"""
LLM Client — abstraction over Anthropic's API.

Handles:
- Message formatting (system prompt + conversation + tools)
- Streaming responses
- Tool call parsing
- Usage tracking

Supports Anthropic as the primary provider (matching pi's default).
OpenAI support can be added later via the same interface.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from mini_pi.config import load_config
from mini_pi.types import (
    AgentEvent,
    AssistantMessage,
    Message,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolDefinition,
    Usage,
)

# ─── Default System Prompt ─────────────────────────────────────────────────
# Mirrors pi's philosophy: minimal, powerful, agentic

DEFAULT_SYSTEM_PROMPT = """You are an expert coding assistant. You help users by reading files, executing commands, and editing code.

Available tools:
- read: Read file contents
- bash: Execute bash commands
- write: Create or overwrite files
- edit: Make precise file edits

Guidelines:
- Use bash for file operations like ls, rg, find
- Use read to examine files
- Be concise in your responses
- Show file paths clearly when working with files
"""


# ─── LLM Client ────────────────────────────────────────────────────────────


class LLMClient:
    """
    Unified LLM client. Currently wraps Anthropic's SDK.

    Usage:
        client = LLMClient(model="claude-sonnet-4-5-20250929")
        response = await client.chat(messages, tools)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        api_key: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 16000,
    ):
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tokens = max_tokens

        # Load config file as fallback
        config = load_config()

        # Resolve API key: param > env var > config file
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or config.get("api_key")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set in ~/.mini-pi/config.json, environment variable, or pass api_key parameter."
            )

        # Resolve base_url: param > env var > config file
        base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL") or config.get("base_url")

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    # ── Message Formatting ─────────────────────────────────────────────

    def _to_anthropic_content(self, content) -> list[dict]:
        """Convert our internal content blocks to Anthropic API format."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}]

        blocks = []
        for block in content:
            if isinstance(block, TextContent):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ThinkingContent):
                blocks.append({"type": "thinking", "thinking": block.thinking})
            elif isinstance(block, ToolCallContent):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.arguments,
                    }
                )
            elif isinstance(block, dict):
                # Already formatted
                blocks.append(block)
        return blocks

    def _to_anthropic_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our message list to Anthropic API format."""
        anthropic_messages = []
        for msg in messages:
            if msg.role == "user":
                content = msg.content if isinstance(msg.content, list) else msg.content
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": content
                        if isinstance(content, str)
                        else self._to_anthropic_content(content),
                    }
                )
            elif msg.role == "assistant":
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": self._to_anthropic_content(msg.content),
                    }
                )
            elif msg.role == "tool_result":
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                                "is_error": msg.is_error,
                            }
                        ],
                    }
                )
        return anthropic_messages

    def _to_anthropic_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert our tool definitions to Anthropic API format."""
        return [t.to_anthropic_schema() for t in tools]

    # ── Streaming Chat ─────────────────────────────────────────────────

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Send a chat request and yield AgentEvents as the response streams.

        Events emitted:
        - text_delta: a chunk of text
        - thinking_delta: a chunk of thinking
        - tool_call: a complete tool call (yielded when full tool_use block received)
        - agent_end: final message with stop_reason and usage
        - error: an error occurred
        """
        try:
            anthropic_messages = self._to_anthropic_messages(messages)
            anthropic_tools = self._to_anthropic_tools(tools) if tools else None

            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=anthropic_messages,
                tools=anthropic_tools,
            ) as stream:
                # Accumulate content blocks as they stream in
                text_accumulator = ""
                current_tool_call: dict[str, Any] | None = None

                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_call = {
                                "id": block.id,
                                "name": block.name,
                                "input": "",
                                "input_json": {},
                            }

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            text_accumulator += delta.text
                            yield AgentEvent(type="text_delta", data=delta.text)
                        elif delta.type == "thinking_delta":
                            yield AgentEvent(type="thinking_delta", data=delta.thinking)
                        elif delta.type == "input_json_delta" and current_tool_call:
                            current_tool_call["input"] += delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_tool_call:
                            # Parse accumulated JSON
                            try:
                                current_tool_call["input_json"] = json.loads(
                                    current_tool_call["input"]
                                )
                            except json.JSONDecodeError:
                                current_tool_call["input_json"] = {}

                            yield AgentEvent(
                                type="tool_call",
                                data=ToolCallContent(
                                    id=current_tool_call["id"],
                                    name=current_tool_call["name"],
                                    arguments=current_tool_call["input_json"],
                                ),
                            )
                            current_tool_call = None

                    elif event.type == "message_stop":
                        # Build final assistant message
                        assistant_msg = AssistantMessage(
                            content=[],
                            model=self.model,
                            stop_reason="end_turn",
                        )

                        if text_accumulator:
                            assistant_msg.content.append(
                                TextContent(text=text_accumulator)
                            )

                        if event.message:
                            assistant_msg.stop_reason = (
                                event.message.stop_reason or "end_turn"
                            )
                            if event.message.usage:
                                assistant_msg.usage = Usage(
                                    input_tokens=event.message.usage.input_tokens,
                                    output_tokens=event.message.usage.output_tokens,
                                    cache_read_tokens=getattr(
                                        event.message.usage,
                                        "cache_read_input_tokens",
                                        0,
                                    )
                                    or 0,
                                    cache_write_tokens=getattr(
                                        event.message.usage,
                                        "cache_creation_input_tokens",
                                        0,
                                    )
                                    or 0,
                                )

                        yield AgentEvent(type="agent_end", data=assistant_msg)

        except anthropic.APIStatusError as e:
            yield AgentEvent(
                type="error",
                data=f"API Error ({e.status_code}): {e.message}",
            )
        except Exception as e:
            yield AgentEvent(type="error", data=str(e))

    # ── Non-streaming Chat ─────────────────────────────────────────────

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> AssistantMessage:
        """
        Non-streaming chat. Collects all events and returns the final message.
        """
        result = AssistantMessage(content=[], model=self.model, stop_reason="end_turn")
        tool_calls: list[ToolCallContent] = []

        async for event in self.chat_stream(messages, tools):
            if event.type == "text_delta":
                result.content.append(TextContent(text=event.data))
            elif event.type == "thinking_delta":
                result.content.append(ThinkingContent(thinking=event.data))
            elif event.type == "tool_call":
                tool_calls.append(event.data)
            elif event.type == "agent_end":
                result = event.data
                # Merge in any tool calls we captured
                for tc in tool_calls:
                    if not any(
                        isinstance(c, ToolCallContent) and c.id == tc.id
                        for c in result.content
                    ):
                        result.content.append(tc)
            elif event.type == "error":
                raise RuntimeError(f"LLM Error: {event.data}")

        return result

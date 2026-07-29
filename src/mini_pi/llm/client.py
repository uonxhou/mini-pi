"""
LLM Client — abstraction over OpenAI-compatible APIs (DeepSeek by default).

Handles:
- Message formatting (system prompt + conversation + tools)
- Streaming responses via SSE
- Tool call parsing
- Usage tracking

Uses the OpenAI SDK, which is compatible with DeepSeek and other
OpenAI-compatible providers.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import openai

from mini_pi.config import (
    PROVIDER_DEFAULTS,
    detect_provider,
    get_auth_path,
    get_config_path,
    load_auth,
    load_config,
    resolve_api_key,
)
from mini_pi.types import (
    AgentEvent,
    AssistantMessage,
    ImageContent,
    Message,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolDefinition,
    Usage,
)

# ─── Default System Prompt ─────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are an expert coding assistant operating inside mini-pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- read: Read file contents
- bash: Execute bash commands (ls, grep, find, etc.)
- edit: Make precise file edits with exact text replacement, including multiple disjoint edits in one call
- write: Create or overwrite files

Guidelines:
- Use bash for file operations like ls, rg, find
- Use read to examine files instead of cat or sed.
- Use edit for precise changes (edits[].oldText must match exactly)
- When changing multiple separate locations in one file, use one edit call with multiple entries in edits[] instead of multiple edit calls
- Keep edits[].oldText as small as possible while still being unique in the file
- Use write only for new files or complete rewrites.
- Be concise in your responses
- Show file paths clearly when working with files
"""

# ─── LLM Client ────────────────────────────────────────────────────────────


class LLMClient:
    """
    Unified LLM client. Uses OpenAI SDK, defaults to DeepSeek API.

    API key priority (pi-style):
        1. api_key parameter (explicit)
        2. ~/.mini-pi/auth.json entry for the detected provider
        3. Environment variable (e.g. DEEPSEEK_API_KEY)

    Usage:
        client = LLMClient(model="deepseek-v4-pro")
        response = await client.chat(messages, tools)
    """

    def __init__(
        self,
        model: str = "deepseek-v4-pro",
        api_key: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 16000,
    ):
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tokens = max_tokens

        # Load configs
        config = load_config()
        auth = load_auth()

        # Detect provider from model + base_url
        provider = detect_provider(model, base_url)
        provider_defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["deepseek"])

        # ── Resolve API key: param > auth.json > env var (pi-style) ──
        if api_key:
            pass  # explicit param wins
        else:
            api_key = resolve_api_key(provider, provider_defaults["env_var"], auth)

        if not api_key:
            raise ValueError(
                f"No API key found for provider '{provider}'.\n"
                f"  • Set {provider_defaults['env_var']} environment variable, or\n"
                f"  • Add to {get_auth_path()}:\n"
                f'    {{"{provider}": {{"type": "api_key", "key": "sk-..."}}}}\n'
                f"  • Pass --api-key flag (CLI) or api_key parameter (SDK)"
            )

        # ── Resolve base_url: param > env > config > provider default ──
        base_url = (
            base_url
            or os.environ.get(f"{provider.upper()}_BASE_URL")
            or config.get("base_url")
            or provider_defaults["base_url"]
        )

        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    # ── Message Formatting ─────────────────────────────────────────────

    def _to_openai_content(self, content) -> str | list[dict]:
        """Convert our internal content blocks to OpenAI API format."""
        if isinstance(content, str):
            return content

        parts: list[dict] = []
        for block in content:
            if isinstance(block, TextContent):
                parts.append({"type": "text", "text": block.text})
            elif isinstance(block, ThinkingContent):
                # OpenAI has no native thinking block; wrap in text
                parts.append(
                    {"type": "text", "text": f"[Thinking: {block.thinking}]"}
                )
            elif isinstance(block, ImageContent):
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{block.mime_type};base64,{block.data}"
                        },
                    }
                )
            elif isinstance(block, dict):
                # Already formatted (tool_use blocks from agent loop)
                # These don't go into OpenAI user/assistant content directly
                pass
        return parts if parts else ""

    def _to_openai_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our message list to OpenAI API format."""
        openai_messages: list[dict] = []

        for msg in messages:
            if msg.role == "user":
                content = msg.content
                if isinstance(content, list):
                    openai_messages.append(
                        {"role": "user", "content": self._to_openai_content(content)}
                    )
                else:
                    openai_messages.append({"role": "user", "content": content})

            elif msg.role == "assistant":
                content_blocks = (
                    msg.content if isinstance(msg.content, list) else [msg.content]
                )

                text_parts: list[str] = []
                tool_calls: list[dict] = []

                for block in content_blocks:
                    if isinstance(block, TextContent):
                        text_parts.append(block.text)
                    elif isinstance(block, ThinkingContent):
                        text_parts.append(f"[Thinking: {block.thinking}]")
                    elif isinstance(block, ToolCallContent):
                        tool_calls.append(
                            {
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": json.dumps(
                                        block.arguments, ensure_ascii=False
                                    ),
                                },
                            }
                        )
                    elif isinstance(block, dict):
                        # Already-formatted tool_use dict from agent loop
                        if block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block["id"],
                                    "type": "function",
                                    "function": {
                                        "name": block["name"],
                                        "arguments": json.dumps(
                                            block.get("input", {}), ensure_ascii=False
                                        ),
                                    },
                                }
                            )

                msg_dict: dict[str, Any] = {"role": "assistant"}
                if text_parts:
                    msg_dict["content"] = (
                        "\n".join(text_parts) if len(text_parts) > 1 else text_parts[0]
                    )
                else:
                    msg_dict["content"] = None
                if tool_calls:
                    msg_dict["tool_calls"] = tool_calls

                openai_messages.append(msg_dict)

            elif msg.role == "tool_result":
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return openai_messages

    def _to_openai_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert our tool definitions to OpenAI API format."""
        return [t.to_openai_schema() for t in tools]

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
        - thinking_delta: a chunk of thinking (R1 models)
        - tool_call: a complete tool call (yielded when finish_reason=tool_calls)
        - agent_end: final message with stop_reason and usage
        - error: an error occurred
        """
        try:
            openai_messages = self._to_openai_messages(messages)
            openai_tools = self._to_openai_tools(tools) if tools else None

            stream = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=openai_messages,
                tools=openai_tools,
                stream=True,
                # Include reasoning_content for deepseek-reasoner models
                extra_body={"include_reasoning": True}
                if "reasoner" in self.model
                else None,
            )

            text_accumulator = ""
            # Tool calls accumulate across chunks by index
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                # ── Text ──────────────────────────────────────────
                if delta.content:
                    text_accumulator += delta.content
                    yield AgentEvent(type="text_delta", data=delta.content)

                # ── Reasoning (DeepSeek R1) ───────────────────────
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield AgentEvent(type="thinking_delta", data=reasoning)

                # ── Tool Calls (accumulate) ───────────────────────
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }

                        acc = tool_calls_accumulator[idx]
                        if tc_delta.id:
                            acc["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                acc["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                acc["arguments"] += tc_delta.function.arguments

                # ── Finish ────────────────────────────────────────
                finish_reason = chunk.choices[0].finish_reason
                if finish_reason:
                    # Yield accumulated tool calls
                    for idx in sorted(tool_calls_accumulator.keys()):
                        acc = tool_calls_accumulator[idx]
                        try:
                            args = json.loads(acc["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        yield AgentEvent(
                            type="tool_call",
                            data=ToolCallContent(
                                id=acc["id"],
                                name=acc["name"],
                                arguments=args,
                            ),
                        )

                    # Map finish_reason
                    stop_reason_map = {
                        "stop": "end_turn",
                        "tool_calls": "tool_use",
                        "length": "max_tokens",
                    }
                    mapped_reason = stop_reason_map.get(
                        finish_reason, finish_reason
                    )

                    # Build final assistant message
                    assistant_msg = AssistantMessage(
                        content=[],
                        model=self.model,
                        stop_reason=mapped_reason,
                    )

                    if text_accumulator:
                        assistant_msg.content.append(
                            TextContent(text=text_accumulator)
                        )

                    if chunk.usage:
                        assistant_msg.usage = Usage(
                            input_tokens=chunk.usage.prompt_tokens,
                            output_tokens=chunk.usage.completion_tokens,
                        )

                    yield AgentEvent(type="agent_end", data=assistant_msg)

        except openai.APIError as e:
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
        result = AssistantMessage(
            content=[], model=self.model, stop_reason="end_turn"
        )
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
                for tc in tool_calls:
                    if not any(
                        isinstance(c, ToolCallContent) and c.id == tc.id
                        for c in result.content
                    ):
                        result.content.append(tc)
            elif event.type == "error":
                raise RuntimeError(f"LLM Error: {event.data}")

        return result

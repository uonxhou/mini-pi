"""
Agent Loop — the core of the coding agent.

Implements the fundamental agentic pattern:
  1. User sends a prompt
  2. System prompt + messages + tools are sent to the LLM
  3. LLM responds with text and/or tool calls
  4. If tool calls: execute them, append results, go to step 2
  5. If no tool calls: the agent has finished

This mirrors pi's agent-core loop.

Usage:
    agent = AgentLoop(client, tools)
    async for event in agent.run("List all Python files"):
        print(event)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from mini_pi.llm.client import LLMClient
from mini_pi.tools.base import ToolRegistry
from mini_pi.types import (
    AgentEvent,
    AssistantMessage,
    Message,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)


class AgentLoop:
    """
    The core agent loop. Manages conversation state and orchestrates
    the LLM ↔ Tool execution cycle.

    Tracks:
    - messages: the full conversation history
    - turns: count of LLM calls made
    - total_usage: cumulative token usage
    """

    def __init__(
        self,
        client: LLMClient,
        tools: ToolRegistry,
        max_turns: int = 50,
    ):
        self.client = client
        self.tools = tools
        self.max_turns = max_turns

        # State
        self.messages: list[Message] = []
        self.turns: int = 0
        self.total_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
        }

    def add_user_message(self, text: str) -> None:
        """Add a user message to the conversation."""
        self.messages.append(UserMessage(content=text))

    async def run(self, prompt: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the agent loop with a user prompt.

        Yields AgentEvents for streaming output.
        """
        # Add user message
        self.add_user_message(prompt)
        yield AgentEvent(type="user_message", data=prompt)

        # Main agent loop
        while self.turns < self.max_turns:
            self.turns += 1
            yield AgentEvent(type="turn_start", data={"turn": self.turns})

            # Collect tool calls from this turn
            assistant_content: list = []
            tool_calls: list[ToolCallContent] = []

            # Call the LLM
            tool_defs = self.tools.get_definitions()

            async for event in self.client.chat_stream(self.messages, tool_defs):
                if event.type == "text_delta":
                    assistant_content.append({"type": "text", "text": event.data})
                    yield event

                elif event.type == "thinking_delta":
                    assistant_content.append(
                        {"type": "thinking", "thinking": event.data}
                    )
                    yield event

                elif event.type == "tool_call":
                    tc = event.data
                    tool_calls.append(tc)
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                    yield AgentEvent(
                        type="tool_call",
                        data={"name": tc.name, "arguments": tc.arguments},
                    )

                elif event.type == "agent_end":
                    assistant_msg: AssistantMessage = event.data
                    # Use the accumulated content for better accuracy
                    assistant_msg.content = assistant_content
                    self.messages.append(assistant_msg)

                    # Track usage
                    if assistant_msg.usage:
                        self.total_usage["input_tokens"] += (
                            assistant_msg.usage.input_tokens
                        )
                        self.total_usage["output_tokens"] += (
                            assistant_msg.usage.output_tokens
                        )

                    yield AgentEvent(
                        type="turn_end",
                        data={
                            "turn": self.turns,
                            "stop_reason": assistant_msg.stop_reason,
                            "usage": assistant_msg.usage,
                        },
                    )

                elif event.type == "error":
                    yield event
                    return  # Stop on error

            # If no tool calls, agent is done
            if not tool_calls:
                yield AgentEvent(type="agent_done", data={"turns": self.turns})
                return

            # Execute tool calls
            tool_results: list[ToolResultMessage] = []
            for tc in tool_calls:
                yield AgentEvent(
                    type="tool_start",
                    data={"name": tc.name, "id": tc.id},
                )

                result = await self.tools.execute(tc.name, tc.id, **tc.arguments)

                tr_msg = ToolResultMessage(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=result.content,
                    is_error=result.is_error,
                )
                tool_results.append(tr_msg)
                self.messages.append(tr_msg)

                yield AgentEvent(
                    type="tool_result",
                    data={
                        "name": tc.name,
                        "id": tc.id,
                        "content": result.content[:500] + "..."
                        if len(result.content) > 500
                        else result.content,
                        "is_error": result.is_error,
                    },
                )

        # Hit max turns
        yield AgentEvent(
            type="error",
            data=f"Reached maximum turns ({self.max_turns}) without completing.",
        )

    def get_messages(self) -> list[Message]:
        """Return the full conversation history."""
        return self.messages

    def get_usage_summary(self) -> str:
        """Return a human-readable usage summary."""
        return (
            f"Turns: {self.turns}\n"
            f"Input tokens: {self.total_usage['input_tokens']:,}\n"
            f"Output tokens: {self.total_usage['output_tokens']:,}"
        )

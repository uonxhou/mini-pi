"""AgentLoop orchestration — the LLM ↔ tool cycle and the history it builds.

The loop's job is to run tools and accumulate messages. It must not rewrite
the assistant message the client produced: doing so is what stripped the
typed content blocks and corrupted history before v0.3.4.
"""

from __future__ import annotations

import asyncio
from typing import Any

from _fakes import FakeToolRegistry, assert_valid_openai_messages

from mini_pi.agent.loop import AgentLoop
from mini_pi.llm.client import LLMClient
from mini_pi.types import (
    AgentEvent,
    AssistantMessage,
    TextContent,
    ToolCallContent,
    Usage,
)


class ScriptedClient:
    """Replays a fixed list of turns, one per chat_stream call."""

    def __init__(self, turns: list[AssistantMessage]) -> None:
        self.turns = turns
        self.calls = 0
        self.seen_history: list[list] = []

    async def chat_stream(self, messages, tools):
        self.seen_history.append(list(messages))
        message = self.turns[self.calls]
        self.calls += 1

        for block in message.content:
            if isinstance(block, TextContent):
                yield AgentEvent(type="text_delta", data=block.text)
            elif isinstance(block, ToolCallContent):
                yield AgentEvent(type="tool_call", data=block)
        yield AgentEvent(type="agent_end", data=message)


def _turn(text: str = "", tool: ToolCallContent | None = None, **kw) -> AssistantMessage:
    content: list = []
    if text:
        content.append(TextContent(text=text))
    if tool is not None:
        content.append(tool)
    return AssistantMessage(
        content=content,
        model="test-model",
        stop_reason="tool_use" if tool else "end_turn",
        usage=kw.get("usage"),
    )


def test_tool_cycle_produces_a_valid_message_sequence():
    """user → assistant(tool_calls) → tool → assistant is the shape the API expects."""
    call = ToolCallContent(id="call_abc", name="bash", arguments={"cmd": "ls"})
    client: Any = ScriptedClient(
        [
            _turn("Checking.", call, usage=Usage(10, 5)),
            _turn("Found 3 files.", usage=Usage(20, 8)),
        ]
    )
    tools: Any = FakeToolRegistry(result="a.py\nb.py\nc.py")
    loop = AgentLoop(client, tools)

    events = asyncio.run(_drain(loop, "list files"))
    assert "agent_done" in events

    out = LLMClient.__new__(LLMClient)._to_openai_messages(loop.messages)
    assert_valid_openai_messages(out)
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "assistant"]


def test_tool_call_ids_are_paired():
    """Every tool result must answer a call the assistant actually made.

    An orphaned tool_call_id is a 400 in its own right, so this guards the
    pairing independently of the content invariant.
    """
    call = ToolCallContent(id="call_xyz", name="read", arguments={"path": "a.py"})
    client: Any = ScriptedClient([_turn("", call), _turn("Done.")])
    tools: Any = FakeToolRegistry(result="file contents")
    loop = AgentLoop(client, tools)

    asyncio.run(_drain(loop, "read a.py"))
    out = LLMClient.__new__(LLMClient)._to_openai_messages(loop.messages)

    declared = {
        tc["id"]
        for m in out
        if m["role"] == "assistant"
        for tc in m.get("tool_calls", [])
    }
    answered = {m["tool_call_id"] for m in out if m["role"] == "tool"}
    assert declared == answered == {"call_xyz"}
    assert tools.calls == [("read", "call_xyz", {"path": "a.py"})]


def test_history_grows_across_turns():
    """Each turn must see everything before it — the point of a conversation."""
    call = ToolCallContent(id="c1", name="bash", arguments={})
    client: Any = ScriptedClient([_turn("working", call), _turn("done")])
    tools: Any = FakeToolRegistry()
    loop = AgentLoop(client, tools)

    asyncio.run(_drain(loop, "go"))

    first, second = client.seen_history
    assert len(first) == 1
    assert len(second) == 3  # user + assistant(tool_call) + tool result
    for snapshot in client.seen_history:
        assert_valid_openai_messages(
            LLMClient.__new__(LLMClient)._to_openai_messages(snapshot)
        )


def test_usage_accumulates():
    call = ToolCallContent(id="c1", name="bash", arguments={})
    client: Any = ScriptedClient(
        [_turn("a", call, usage=Usage(10, 5)), _turn("b", usage=Usage(20, 8))]
    )
    tools: Any = FakeToolRegistry()
    loop = AgentLoop(client, tools)

    asyncio.run(_drain(loop, "go"))
    assert loop.total_usage == {"input_tokens": 30, "output_tokens": 13}


def test_loop_stops_without_tool_calls():
    """A text-only reply ends the loop instead of spinning to max_turns."""
    client: Any = ScriptedClient([_turn("Just answering.")])
    tools: Any = FakeToolRegistry()
    loop = AgentLoop(client, tools)

    events = asyncio.run(_drain(loop, "hi"))
    assert events.count("turn_start") == 1
    assert "agent_done" in events


def test_tool_errors_still_reach_history():
    """A failing tool must be reported back, not dropped — the model needs to see it."""
    call = ToolCallContent(id="c1", name="bash", arguments={"cmd": "nope"})
    client: Any = ScriptedClient([_turn("trying", call), _turn("that failed")])
    tools: Any = FakeToolRegistry(result="command not found", is_error=True)
    loop = AgentLoop(client, tools)

    asyncio.run(_drain(loop, "run it"))
    out = LLMClient.__new__(LLMClient)._to_openai_messages(loop.messages)

    assert_valid_openai_messages(out)
    tool_msg = next(m for m in out if m["role"] == "tool")
    assert tool_msg["content"] == "command not found"


async def _drain(loop: AgentLoop, prompt: str) -> list[str]:
    return [event.type async for event in loop.run(prompt)]

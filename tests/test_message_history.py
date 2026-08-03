"""Conversation-history construction — the layer that broke multi-turn chat.

Before v0.3.4 the agent loop rebuilt AssistantMessage.content from streamed
deltas as untyped dicts, which _to_openai_messages silently dropped. The
result was {"role": "assistant", "content": null} in history, rejected by
the API on every request from then on.

These tests pin the contract: whatever the model streams back, the message
that lands in history must survive a round trip through _to_openai_messages.
"""

from __future__ import annotations

import asyncio
import json

from _fakes import (
    assert_valid_openai_messages,
    chunk,
    fake_client,
    run_stream,
    tool_call_delta,
    usage,
)

from mini_pi.types import UserMessage


def test_plain_text_reply_keeps_its_content():
    """The exact regression: a text-only reply must not become content=null."""
    history = [UserMessage(content="hi")]
    client = fake_client(
        [chunk("Hi"), chunk(" there!"), chunk(" 👋", finish="stop")]
    )
    asyncio.run(run_stream(client, history))

    out = client._to_openai_messages(history)
    assert_valid_openai_messages(out)

    assistant = out[1]
    assert assistant["content"] == "Hi there! 👋"
    assert "tool_calls" not in assistant


def test_second_turn_history_is_accepted():
    """Reproduces the reported failure: turn 1 fine, turn 2 exploded.

    The 400 surfaced on the *second* request, because that is when the bad
    message from turn 1 was first replayed. Asserting only on turn 1 would
    have missed the bug entirely.
    """
    history = [UserMessage(content="hi")]
    client = fake_client([chunk("Hi there!", finish="stop")])
    asyncio.run(run_stream(client, history))

    history.append(UserMessage(content="江苏常州天气怎么样？"))
    out = client._to_openai_messages(history)

    assert_valid_openai_messages(out)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]


def test_tool_call_reply_carries_its_calls():
    """A tool-only reply legitimately has content=None — but must have tool_calls.

    Arguments are split across chunks, as real providers do, so the
    accumulator is genuinely exercised.
    """
    history = [UserMessage(content="read a.py")]
    client = fake_client(
        [
            chunk(tool_calls=[tool_call_delta(0, "call_1", "read", '{"path"')]),
            chunk(tool_calls=[tool_call_delta(0, arguments=':"a.py"}')]),
            chunk(finish="tool_calls"),
        ]
    )
    asyncio.run(run_stream(client, history))

    out = client._to_openai_messages(history)
    assert_valid_openai_messages(out)

    call = out[1]["tool_calls"][0]
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "read"
    assert json.loads(call["function"]["arguments"]) == {"path": "a.py"}


def test_text_and_tool_call_survive_together():
    """Mixed replies must keep both halves; dropping either corrupts the turn."""
    history = [UserMessage(content="list files")]
    client = fake_client(
        [
            chunk("Let me check."),
            chunk(tool_calls=[tool_call_delta(0, "call_2", "bash", '{"cmd":"ls"}')]),
            chunk(finish="tool_calls"),
        ]
    )
    asyncio.run(run_stream(client, history))

    out = client._to_openai_messages(history)
    assert_valid_openai_messages(out)

    assistant = out[1]
    assert assistant["content"] == "Let me check."
    assert len(assistant["tool_calls"]) == 1


def test_reasoning_round_trips_on_a_top_level_field():
    """Reasoning must reach the UI AND survive the round-trip.

    DeepSeek v4 changed the contract: `reasoning_content` must be sent back
    on every subsequent request when tools are involved (else HTTP 400), and
    the legacy `include_reasoning` flag is gone. We stream it live to the UI
    while it arrives and persist it as a top-level field on AssistantMessage
    so `_to_openai_messages` can re-emit it unchanged. It must NOT also leak
    into `content` — that would double the cost and look like a tool round.
    """
    history = [UserMessage(content="think about it")]
    client = fake_client(
        [
            chunk(reasoning="Let me reason..."),
            chunk("Done.", finish="stop"),
        ]
    )

    async def collect():
        events = []
        async for event in client.chat_stream(history, None):
            events.append(event)
            if event.type == "agent_end":
                history.append(event.data)
        return events

    events = asyncio.run(collect())

    assert any(e.type == "thinking_delta" for e in events), "reasoning never surfaced"

    out = client._to_openai_messages(history)
    assert_valid_openai_messages(out)

    # Survives the round-trip as a sibling of `content`, not inside it.
    assert out[1]["reasoning_content"] == "Let me reason..."
    assert out[1]["content"] == "Done."


def test_usage_is_recorded():
    """Token accounting must survive the message build."""
    history = [UserMessage(content="hi")]
    client = fake_client([chunk("ok", finish="stop", usage=usage(12, 34))])
    message = asyncio.run(run_stream(client, history))

    assert message.usage is not None
    assert message.usage.input_tokens == 12
    assert message.usage.output_tokens == 34


def test_malformed_tool_arguments_do_not_crash():
    """Truncated JSON must degrade to {} rather than kill the stream."""
    history = [UserMessage(content="go")]
    client = fake_client(
        [
            chunk(tool_calls=[tool_call_delta(0, "call_3", "bash", '{"cmd": "l')]),
            chunk(finish="tool_calls"),
        ]
    )
    asyncio.run(run_stream(client, history))

    out = client._to_openai_messages(history)
    assert_valid_openai_messages(out)
    assert json.loads(out[1]["tool_calls"][0]["function"]["arguments"]) == {}

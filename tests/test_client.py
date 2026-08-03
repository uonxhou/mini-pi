"""Client-layer tests that complement test_message_history.py.

The history tests pin the round-trip contract; this module covers behaviours
the history suite deliberately leaves out:

  - the ``thinking`` toggle actually controls ``extra_body``
  - ``reasoning_content`` is omitted from the wire when it is None or empty
    (not silently serialised as ``""`` or ``null``)
  - ``chat()`` — the non-streaming wrapper — is a thin pass-through over
    ``chat_stream()`` and refuses to invent an empty AssistantMessage when the
    stream ends without a terminal event
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from _fakes import _FakeStream, chunk, fake_client, run_stream

from mini_pi.llm.client import LLMClient
from mini_pi.types import AgentEvent, AssistantMessage, TextContent


# ── thinking toggle ─────────────────────────────────────────────────────────


def _client_capturing_kwargs(chunks, *, thinking: bool):
    """Like fake_client but records the kwargs of chat.completions.create().

    The shared fake_client drops kwargs on the floor (it only returns a stream),
    which is right for accumulation tests but not for asserting on extra_body.
    """
    captured: dict = {}

    async def create(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeStream(list(chunks))

    client = LLMClient.__new__(LLMClient)
    client.model = "test-model"
    client.max_tokens = 100
    client.system_prompt = "test system prompt"
    client.thinking = thinking
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return client, captured


def test_thinking_enabled_by_default():
    """The constructor default (``thinking=True``) must produce the v4 wire
    format ``{"thinking": {"type": "enabled"}}`` — not the legacy
    ``{"include_reasoning": True}`` and not the absence of the field.
    """
    client, captured = _client_capturing_kwargs(
        [chunk("hi", finish="stop")], thinking=True
    )

    asyncio.run(_drain(client))

    assert captured["kwargs"]["extra_body"] == {"thinking": {"type": "enabled"}}


def test_thinking_disabled_when_constructor_arg_is_false():
    """The only way to opt out of v4 reasoning is to pass ``thinking=False``
    at construction; the wire field must read ``"disabled"`` verbatim.
    """
    client, captured = _client_capturing_kwargs(
        [chunk("hi", finish="stop")], thinking=False
    )

    asyncio.run(_drain(client))

    assert captured["kwargs"]["extra_body"] == {"thinking": {"type": "disabled"}}


# ── reasoning_content: omitted when absent ──────────────────────────────────


def test_reasoning_content_is_none_when_no_reasoning_streamed():
    """A non-reasoning reply must not be promoted to reasoning_content="".
    An empty string would still satisfy ``if msg.reasoning_content:`` guards
    downstream, so we pin ``None`` to keep the falsy contract honest.
    """
    history = []
    client = fake_client([chunk("Just an answer.", finish="stop")])
    message = asyncio.run(run_stream(client, history))

    assert message.reasoning_content is None


def test_empty_reasoning_content_is_not_emitted_to_wire():
    """Even if a caller forces ``reasoning_content=""`` (empty string), it must
    not appear on the wire — v4 treats ``""`` as an actually-empty reasoning
    payload, distinct from "no reasoning happened", and downstream code paths
    use ``if msg.reasoning_content:`` to gate emission.
    """
    client = fake_client([])
    msg = AssistantMessage(
        content=[TextContent(text="answer")], reasoning_content=""
    )

    out = client._to_openai_messages([msg])

    assert "reasoning_content" not in out[0]


# ── chat(): non-streaming wrapper ───────────────────────────────────────────


def test_chat_returns_the_agent_end_message_unchanged():
    """chat() must forward the AssistantMessage yielded in chat_stream's
    agent_end event verbatim — not a separately-built copy. Identity check
    pins this so a future refactor can't silently start reconstructing it.
    """
    expected = AssistantMessage(
        content=[TextContent(text="hello")],
        reasoning_content="I thought",
        model="test-model",
        stop_reason="end_turn",
    )
    client = LLMClient.__new__(LLMClient)
    client.model = "test-model"
    client.max_tokens = 100
    client.system_prompt = "test system prompt"
    client.thinking = True

    async def fake_stream(messages, tools=None):
        yield AgentEvent(type="agent_end", data=expected)

    client.chat_stream = fake_stream  # type: ignore[method-assign]

    result = asyncio.run(client.chat([]))

    assert result is expected
    assert result.reasoning_content == "I thought"


def test_chat_raises_runtime_error_on_error_event():
    """chat() must propagate stream errors as RuntimeError; otherwise a failed
    request silently returns an empty AssistantMessage and the next turn dies
    with a confusing 400 instead of a clear cause.
    """
    client = LLMClient.__new__(LLMClient)
    client.model = "test-model"
    client.max_tokens = 100
    client.system_prompt = "test system prompt"
    client.thinking = True

    async def fake_stream(messages, tools=None):
        yield AgentEvent(type="error", data="upstream blew up")

    client.chat_stream = fake_stream  # type: ignore[method-assign]

    try:
        asyncio.run(client.chat([]))
    except RuntimeError as e:
        assert "upstream blew up" in str(e)
    else:
        raise AssertionError("chat() should have raised")


def test_chat_raises_when_stream_ends_without_terminal_event():
    """chat_stream is contractually required to emit exactly one of
    {agent_end, error} before terminating. If it doesn't, chat() must raise —
    returning an empty AssistantMessage would let the next turn hit a 400
    with no indication of why.
    """
    client = LLMClient.__new__(LLMClient)
    client.model = "test-model"
    client.max_tokens = 100
    client.system_prompt = "test system prompt"
    client.thinking = True

    async def fake_stream(messages, tools=None):
        return
        yield  # noqa: makes this an async generator

    client.chat_stream = fake_stream  # type: ignore[method-assign]

    try:
        asyncio.run(client.chat([]))
    except RuntimeError as e:
        assert "stream ended without final message" in str(e)
    else:
        raise AssertionError("chat() should have raised")


# ── helpers ─────────────────────────────────────────────────────────────────


async def _drain(client: LLMClient) -> None:
    """Consume chat_stream to completion, ignoring events."""
    async for _ in client.chat_stream([], None):
        pass
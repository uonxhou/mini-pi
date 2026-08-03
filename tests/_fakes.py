"""Test doubles for the OpenAI streaming API and mini-pi's tool layer.

These let the tests drive the real accumulation and message-formatting code
paths without network access or an API key, so the suite is fast, offline,
and free to run.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mini_pi.llm.client import LLMClient
from mini_pi.types import AssistantMessage, Message


def chunk(
    content: str | None = None,
    tool_calls: list | None = None,
    finish: str | None = None,
    usage: Any = None,
    reasoning: str | None = None,
) -> SimpleNamespace:
    """Build one streaming chunk shaped like the OpenAI SDK's."""
    delta = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)],
        usage=usage,
    )


def tool_call_delta(
    index: int,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    """Build one tool-call fragment.

    Real providers split a single call across several chunks — the id and
    name arrive first, then the JSON arguments in pieces — so tests should
    too, otherwise the accumulator logic is never exercised.
    """
    function = (
        SimpleNamespace(name=name, arguments=arguments)
        if (name or arguments)
        else None
    )
    return SimpleNamespace(index=index, id=id, function=function)


def usage(prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """Build a usage payload as the SDK reports it."""
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


class _FakeStream:
    """Async-iterable over a fixed list of chunks."""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c

        return gen()


def fake_client(chunks: list | tuple = ()) -> LLMClient:
    """An LLMClient wired to a scripted stream.

    __init__ is bypassed on purpose: it resolves credentials and a base URL,
    neither of which exist in CI. Everything below __init__ — accumulation,
    message formatting — is the real implementation.
    """
    client = LLMClient.__new__(LLMClient)
    client.model = "test-model"
    client.max_tokens = 100
    client.system_prompt = "test system prompt"
    # Mirrors LLMClient.__init__ default; required because the v4 reasoning
    # toggle is read off `self.thinking` inside chat_stream.
    client.thinking = True

    async def create(**_kwargs):
        return _FakeStream(list(chunks))

    client._client = SimpleNamespace(  # type: ignore[attr-defined]
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return client


async def run_stream(client: LLMClient, history: list[Message]) -> AssistantMessage:
    """Drive chat_stream to completion and append the assistant message.

    Mirrors what AgentLoop does, so tests of the client layer stay honest
    about how the message actually reaches history.
    """
    message = None
    async for event in client.chat_stream(history, None):
        if event.type == "error":
            raise AssertionError(f"unexpected stream error: {event.data}")
        if event.type == "agent_end":
            message = event.data

    assert message is not None, "stream ended without emitting agent_end"
    history.append(message)
    return message


class FakeToolRegistry:
    """Minimal stand-in for ToolRegistry that records what it was asked to run."""

    def __init__(self, result: str = "ok", is_error: bool = False) -> None:
        self.result = result
        self.is_error = is_error
        self.calls: list[tuple[str, str, dict]] = []

    def get_definitions(self) -> list:
        return []

    async def execute(self, name: str, call_id: str, **kwargs):
        self.calls.append((name, call_id, kwargs))
        return SimpleNamespace(content=self.result, is_error=self.is_error)


def assert_valid_openai_messages(messages: list[dict]) -> None:
    """Assert the invariant the OpenAI-compatible API enforces on assistant turns.

    An assistant message must carry content or tool_calls. Violating this is
    what broke every multi-turn session before v0.3.4: one contentless message
    entered history and poisoned every subsequent request, not just the next.
    """
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        has_content = m.get("content") not in (None, "")
        has_tool_calls = bool(m.get("tool_calls"))
        assert has_content or has_tool_calls, (
            f"messages[{i}] has neither content nor tool_calls, "
            f"which the API rejects with HTTP 400: {m!r}"
        )

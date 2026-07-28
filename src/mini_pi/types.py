"""
Core type definitions for mini-pi.

These types mirror pi's message format, covering:
- Content blocks (text, image, tool_use, tool_result, thinking)
- Messages (user, assistant)
- Tool definitions and schemas
- Usage and cost tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union

# ─── Content Blocks ────────────────────────────────────────────────────────


@dataclass
class TextContent:
    """Plain text content block."""

    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ImageContent:
    """Image content block (base64 encoded)."""

    type: Literal["image"] = "image"
    data: str = ""  # base64 encoded
    mime_type: str = "image/png"


@dataclass
class ThinkingContent:
    """Extended thinking / reasoning content block."""

    type: Literal["thinking"] = "thinking"
    thinking: str = ""


@dataclass
class ToolCallContent:
    """A tool call requested by the assistant."""

    type: Literal["tool_call"] = "tool_call"
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultContent:
    """The result of executing a tool call."""

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str = ""
    content: str = ""
    is_error: bool = False


# Union of all content block types
ContentBlock = TextContent | ImageContent | ThinkingContent | ToolCallContent | ToolResultContent


# ─── Messages ──────────────────────────────────────────────────────────────


@dataclass
class UserMessage:
    """A message from the user."""

    role: Literal["user"] = "user"
    content: str | list[TextContent | ImageContent] = ""


@dataclass
class AssistantMessage:
    """A message from the assistant (may contain text, thinking, and tool calls)."""

    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ThinkingContent | ToolCallContent] = field(
        default_factory=list
    )
    model: str = ""
    stop_reason: str = ""  # "end_turn", "tool_use", "max_tokens", "stop_sequence"
    usage: Usage | None = None


@dataclass
class ToolResultMessage:
    """The result of a tool execution, sent back to the LLM."""

    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    content: str = ""
    is_error: bool = False


# Union of all message types
Message = UserMessage | AssistantMessage | ToolResultMessage


# ─── Usage & Cost ──────────────────────────────────────────────────────────


@dataclass
class Usage:
    """Token usage and cost for an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


# ─── Tool Definition ───────────────────────────────────────────────────────


@dataclass
class ToolParameter:
    """A parameter in a tool's JSON Schema."""

    type: str = "string"
    description: str = ""
    enum: list[str] | None = None
    required: bool = True


@dataclass
class ToolDefinition:
    """Definition of a tool that the LLM can call."""

    name: str
    description: str
    parameters: dict[str, ToolParameter] = field(default_factory=dict)

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI-compatible tool schema."""
        properties = {}
        required = []
        for pname, param in self.parameters.items():
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[pname] = prop
            if param.required:
                required.append(pname)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_schema(self) -> dict:
        """Convert to Anthropic-compatible tool schema."""
        properties = {}
        required = []
        for pname, param in self.parameters.items():
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[pname] = prop
            if param.required:
                required.append(pname)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


# ─── Agent Event ──────────────────────────────────────────────────────────


@dataclass
class AgentEvent:
    """An event emitted during agent execution (for streaming / UI)."""

    type: str  # "text_delta", "thinking_delta", "tool_call", "tool_result", "agent_end", "error"
    data: Any = None

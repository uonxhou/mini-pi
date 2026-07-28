"""
Base classes for the tool system.

Each tool has:
- A name, description, and parameter schema (ToolDefinition)
- An execute method that takes parameters and returns a ToolResult

The ToolRegistry manages tool lookup and execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from mini_pi.types import ToolDefinition, ToolParameter


# ─── Tool Result ───────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Result of executing a tool."""
    content: str = ""
    is_error: bool = False
    details: dict[str, Any] = field(default_factory=dict)


# ─── Base Tool ─────────────────────────────────────────────────────────────

class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str = ""
    description: str = ""
    parameters: dict[str, ToolParameter] = {}

    def get_definition(self) -> ToolDefinition:
        """Return the ToolDefinition for this tool."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...


# ─── Tool Registry ─────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Manages a collection of tools. Provides lookup, definition listing,
    and execution routing.
    """

    def __init__(self, tools: list[BaseTool] | None = None):
        self._tools: dict[str, BaseTool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """Register a tool by name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_definitions(self) -> list[ToolDefinition]:
        """Return all tool definitions (for sending to the LLM)."""
        return [t.get_definition() for t in self._tools.values()]

    def get_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, tool_call_id: str, **kwargs) -> ToolResult:
        """Execute a tool by name, returning its result."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                content=f"Error: Unknown tool '{name}'. Available: {', '.join(self._tools.keys())}",
                is_error=True,
            )
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                content=f"Tool execution error: {e}",
                is_error=True,
            )

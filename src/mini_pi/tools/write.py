"""
Write tool — creates or overwrites files.

Matches pi's write tool:
- Automatically creates parent directories
- Overwrites existing files
"""

from __future__ import annotations

from pathlib import Path

from mini_pi.tools.base import BaseTool, ToolResult
from mini_pi.types import ToolParameter


class WriteTool(BaseTool):
    name = "write"
    description = (
        "Write content to a file. Creates the file if it doesn't exist, "
        "overwrites if it does. Automatically creates parent directories."
    )
    parameters = {
        "path": ToolParameter(
            type="string",
            description="Path to the file to write (relative or absolute)",
        ),
        "content": ToolParameter(
            type="string",
            description="Content to write to the file",
        ),
    }

    def __init__(self, cwd: str | None = None):
        self.cwd = Path(cwd) if cwd else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to cwd."""
        p = Path(path)
        if not p.is_absolute():
            p = self.cwd / p
        return p.resolve()

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            file_path = self._resolve_path(path)

            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists
            existed = file_path.exists()

            # Write the file
            file_path.write_text(content, encoding="utf-8")

            size = file_path.stat().st_size
            lines = content.count("\n") + 1

            return ToolResult(
                content=(
                    f"{'Updated' if existed else 'Created'} file: {path}\n"
                    f"  Lines: {lines}\n"
                    f"  Size: {size} bytes"
                ),
                details={
                    "path": str(file_path),
                    "existed": existed,
                    "size_bytes": size,
                    "lines": lines,
                },
            )

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied: {path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error writing file: {e}",
                is_error=True,
            )

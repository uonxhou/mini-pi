"""
Read tool — reads file contents, supporting text and images.

Matches pi's read tool: supports offset/limit for large files,
and detects image files to send as base64 attachments.
"""

from __future__ import annotations

import base64
from pathlib import Path

from mini_pi.tools.base import BaseTool, ToolResult
from mini_pi.types import ToolParameter


# File extensions that should be treated as images
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# Maximum text file size (50KB), matching pi's behavior
MAX_TEXT_SIZE = 50 * 1024
# Maximum lines to return (2000), matching pi's behavior
MAX_LINES = 2000


class ReadTool(BaseTool):
    name = "read"
    description = (
        "Read the contents of a file. Supports text files and images "
        "(jpg, png, gif, webp, bmp). Images are returned as base64. "
        "For text files, output is truncated to 2000 lines or 50KB. "
        "Use offset/limit for large files."
    )
    parameters = {
        "path": ToolParameter(
            type="string",
            description="Path to the file to read (relative or absolute)",
        ),
        "offset": ToolParameter(
            type="number",
            description="Line number to start reading from (1-indexed)",
            required=False,
        ),
        "limit": ToolParameter(
            type="number",
            description="Maximum number of lines to read",
            required=False,
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

    async def execute(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    content=f"Error: File not found: {path}",
                    is_error=True,
                )

            if file_path.is_dir():
                return ToolResult(
                    content=f"Error: '{path}' is a directory. Use ls to list directory contents.",
                    is_error=True,
                )

            # Check if it's an image
            suffix = file_path.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                return await self._read_image(file_path)

            return await self._read_text(file_path, offset, limit)

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied: {path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error reading file: {e}",
                is_error=True,
            )

    async def _read_text(self, file_path: Path, offset: int | None, limit: int | None) -> ToolResult:
        """Read a text file with optional offset/limit."""
        try:
            # Check file size first
            file_size = file_path.stat().st_size
            if file_size > MAX_TEXT_SIZE:
                # Read only first MAX_TEXT_SIZE bytes for large files
                raw = file_path.read_bytes()[:MAX_TEXT_SIZE]
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    content = raw.decode("utf-8", errors="replace")
                truncated_size = True
            else:
                content = file_path.read_text("utf-8")
                truncated_size = False

            lines = content.split("\n")
            total_lines = len(lines)

            # Apply offset (1-indexed)
            start = max(0, (offset or 1) - 1)

            # Apply limit
            if limit is not None:
                end = min(start + limit, total_lines)
            else:
                end = min(start + MAX_LINES, total_lines)

            selected = lines[start:end]
            result = "\n".join(selected)

            # Add truncation notices
            notices = []
            if truncated_size:
                notices.append(f"[File exceeds 50KB. Only first 50KB shown.]")
            if end < total_lines:
                notices.append(
                    f"[Showing lines {start + 1}-{end} of {total_lines}. "
                    f"Use offset/limit to read more.]"
                )

            if notices:
                if result:
                    result += "\n\n" + "\n".join(notices)
                else:
                    result = "\n".join(notices)

            return ToolResult(
                content=result,
                details={
                    "path": str(file_path),
                    "total_lines": total_lines,
                    "lines_shown": end - start,
                    "start_line": start + 1,
                    "truncated": truncated_size or end < total_lines,
                },
            )

        except UnicodeDecodeError:
            return ToolResult(
                content=f"[Binary file: {file_path.name}]",
                details={"path": str(file_path), "binary": True},
            )

    async def _read_image(self, file_path: Path) -> ToolResult:
        """Read an image file and return base64 data."""
        data = file_path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(file_path.suffix.lower(), "image/png")

        return ToolResult(
            content=f"[Image: {file_path.name} ({len(data)} bytes, {mime_type})]\n"
                     f"Base64 data: {encoded[:100]}...",
            details={
                "path": str(file_path),
                "image": True,
                "mime_type": mime_type,
                "size_bytes": len(data),
                "base64": encoded,
            },
        )

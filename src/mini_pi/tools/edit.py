"""
Edit tool — makes precise text replacements in files.

This is pi's most innovative built-in tool. Instead of rewriting entire files,
it allows the LLM to specify exact text replacements. Multiple disjoint edits
in one call.

Key behavior:
- Each edit's oldText must match exactly one region in the file
- Edits must not overlap
- Multiple edits can be made in a single call
- Matches the original file (not intermediate states) for all edits
"""

from __future__ import annotations

import difflib
from pathlib import Path

from mini_pi.tools.base import BaseTool, ToolResult
from mini_pi.types import ToolParameter


class EditTool(BaseTool):
    name = "edit"
    description = (
        "Edit a single file using exact text replacement. "
        "Every edits[].oldText must match a unique, non-overlapping region "
        "of the original file. If two changes affect the same block or nearby "
        "lines, merge them into one edit instead of emitting overlapping edits. "
        "Do not include large unchanged regions just to connect distant changes."
    )
    parameters = {
        "path": ToolParameter(
            type="string",
            description="Path to the file to edit (relative or absolute)",
        ),
        "edits": ToolParameter(
            type="array",
            description=(
                "One or more targeted replacements. Each edit is matched against "
                "the original file, not incrementally. Each has oldText and newText."
            ),
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

    async def execute(self, path: str, edits: list[dict]) -> ToolResult:
        """
        Apply edits to a file.

        edits is a list of dicts, each with:
        - oldText: exact text to find and replace
        - newText: replacement text
        """
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(
                    content=f"Error: File not found: {path}",
                    is_error=True,
                )

            original = file_path.read_text("utf-8")

            # Validate all edits before applying any
            errors = self._validate_edits(original, edits)
            if errors:
                return ToolResult(
                    content="Error: Edit validation failed:\n" + "\n".join(f"  - {e}" for e in errors),
                    is_error=True,
                )

            # Apply edits (all match against original)
            result = original
            applied_count = 0
            for edit in edits:
                old_text = edit["oldText"]
                new_text = edit["newText"]

                # Find the unique match in the *original* file
                count = original.count(old_text)
                if count == 0:
                    return ToolResult(
                        content=f"Error: oldText not found in file:\n{old_text[:200]}",
                        is_error=True,
                    )
                if count > 1:
                    return ToolResult(
                        content=f"Error: oldText matches {count} locations (must be unique). "
                                f"Include more surrounding context to make it unique.",
                        is_error=True,
                    )

                # Apply the replacement to the result
                result = result.replace(old_text, new_text, 1)
                applied_count += 1

            # Generate a unified diff for display
            diff = self._generate_diff(original, result, str(file_path))

            # Write back
            file_path.write_text(result, "utf-8")

            return ToolResult(
                content=f"Applied {applied_count} edit(s) to {path}:\n\n{diff}",
                details={
                    "path": str(file_path),
                    "edits_applied": applied_count,
                    "diff": diff,
                },
            )

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied: {path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error editing file: {e}",
                is_error=True,
            )

    def _validate_edits(self, original: str, edits: list[dict]) -> list[str]:
        """Validate that all edits are well-formed and non-overlapping."""
        errors = []

        for i, edit in enumerate(edits):
            if "oldText" not in edit or "newText" not in edit:
                errors.append(f"Edit {i + 1}: missing 'oldText' or 'newText'")
                continue

            old = edit["oldText"]
            new = edit["newText"]

            if not old:
                errors.append(f"Edit {i + 1}: oldText must not be empty")
                continue

            if old == new:
                errors.append(f"Edit {i + 1}: oldText and newText are identical (no change)")

            # Check uniqueness in original
            count = original.count(old)
            if count == 0:
                errors.append(
                    f"Edit {i + 1}: oldText not found in file. "
                    f"First 100 chars: '{old[:100]}'"
                )
            elif count > 1:
                errors.append(
                    f"Edit {i + 1}: oldText found {count} times (must be unique). "
                    f"Add more surrounding context."
                )

        # Check for overlaps in the original file
        if len(edits) > 1 and not errors:
            spans = []
            for edit in edits:
                idx = original.index(edit["oldText"])
                spans.append((idx, idx + len(edit["oldText"]), edit["oldText"][:50]))

            # Sort by position
            spans.sort()

            for i in range(len(spans) - 1):
                if spans[i][1] > spans[i + 1][0]:
                    errors.append(
                        f"Edits overlap in the original file. Merge them into one edit. "
                        f"Overlap: '{spans[i][2]}...' with '{spans[i+1][2]}...'"
                    )

        return errors

    def _generate_diff(self, original: str, modified: str, filename: str) -> str:
        """Generate a unified diff."""
        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        ))
        return "".join(diff_lines)

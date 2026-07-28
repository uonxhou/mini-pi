"""
Bash tool — executes shell commands.

Matches pi's bash tool:
- Runs commands in a subprocess
- Captures stdout and stderr
- Supports timeout
- Truncates output at 50KB (matching pi's behavior)
- Injects session info as environment variables (PI_SESSION_ID, etc.)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from mini_pi.tools.base import BaseTool, ToolResult
from mini_pi.types import ToolParameter

# Maximum output size (50KB, matching pi)
MAX_OUTPUT_SIZE = 50 * 1024


class BashTool(BaseTool):
    name = "bash"
    description = (
        "Execute a bash command in the current working directory. "
        "Returns stdout and stderr. Output is truncated to last 2000 lines or 50KB "
        "(whichever is hit first). If truncated, full output is saved to a temp file. "
        "Optionally provide a timeout in seconds."
    )
    parameters = {
        "command": ToolParameter(
            type="string",
            description="Bash command to execute",
        ),
        "timeout": ToolParameter(
            type="number",
            description="Timeout in seconds (optional, default: 120)",
            required=False,
        ),
    }

    def __init__(self, cwd: str | None = None, session_id: str = ""):
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.session_id = session_id

    async def execute(self, command: str, timeout: float = 120) -> ToolResult:
        try:
            # Run the command in a subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.cwd),
                env={
                    **os.environ,
                    "PI_SESSION_ID": self.session_id,
                },
                executable=shutil.which("bash") or "/bin/bash",
            )

            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    content=f"Error: Command timed out after {timeout}s",
                    is_error=True,
                    details={"exit_code": -1, "timed_out": True},
                )

            exit_code = process.returncode or 0
            output = stdout_bytes.decode("utf-8", errors="replace")

            # Truncate if needed
            truncated = False
            full_output_path = None

            if len(output) > MAX_OUTPUT_SIZE:
                truncated = True
                # Save full output to a temp file
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    prefix="mini-pi-bash-",
                    suffix=".txt",
                    delete=False,
                ) as f:
                    f.write(output)
                    full_output_path = f.name

                # Truncate: keep last ~2000 lines worth from the end
                output = output[-MAX_OUTPUT_SIZE:]
                # Also try to start at a line boundary
                first_newline = output.find("\n")
                if first_newline > 0:
                    output = output[first_newline + 1:]

                output = (
                    f"[Output truncated. Full output saved to: {full_output_path}]\n\n"
                    + output
                )

            return ToolResult(
                content=output if output else "(no output)",
                is_error=exit_code != 0,
                details={
                    "exit_code": exit_code,
                    "truncated": truncated,
                    "full_output_path": full_output_path,
                    "timed_out": False,
                },
            )

        except Exception as e:
            return ToolResult(
                content=f"Error executing command: {e}",
                is_error=True,
                details={"exit_code": -1},
            )

"""CLI-level regressions: platform portability and version reporting.

Both bugs here shipped to PyPI once. The readline crash made mini-pi
completely unusable on Windows; the hardcoded version silently drifted
three releases behind.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from importlib.metadata import version

import mini_pi
from mini_pi.cli import print_banner

ANSI = re.compile(r"\033\[[0-9;]*m")


def test_cli_imports_without_readline():
    """Regression: `import readline` at module scope crashed the whole CLI.

    readline is a Unix-only stdlib module. On Windows the import raised
    ModuleNotFoundError before argparse ever ran, so even `mini-pi --help`
    was unreachable.

    Runs in a subprocess because readline is almost certainly already in
    sys.modules by the time this test executes — blocking it in-process
    would not reproduce a cold import.
    """
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name == "readline":
                    raise ImportError("simulated: platform has no readline")
                return None

        sys.meta_path.insert(0, Blocker())
        sys.modules.pop("readline", None)

        import mini_pi.cli
        assert callable(mini_pi.cli.main)
        print("IMPORT_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"cli import failed without readline:\n{result.stderr}"
    )
    assert "IMPORT_OK" in result.stdout


def test_version_matches_distribution_metadata():
    """Regression: the version was hardcoded in two files and both drifted.

    pyproject.toml is the single source of truth; __version__ reads it back
    from the installed distribution.
    """
    assert mini_pi.__version__ == version("mini-pi")
    assert mini_pi.__version__ != "0.0.0+dev", (
        "package metadata unavailable — run the suite against an installed "
        "package (uv run pytest), not a bare source tree"
    )


def test_banner_is_aligned(capsys):
    """Regression: the box was 29 wide around 27-wide rows.

    Centring is computed at runtime now, so a longer version string cannot
    reintroduce the skew.
    """
    print_banner()
    lines = [
        ANSI.sub("", line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert len(lines) == 4, f"expected a 4-line banner, got {lines}"
    widths = {len(line) for line in lines}
    assert len(widths) == 1, f"banner rows have differing widths: {widths}"


def test_banner_shows_current_version(capsys):
    print_banner()
    out = ANSI.sub("", capsys.readouterr().out)
    assert f"mini-pi v{mini_pi.__version__}" in out

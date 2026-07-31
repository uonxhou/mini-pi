"""mini-pi: A minimal AI coding agent built from scratch for learning."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth is pyproject.toml — read it back from the
    # installed distribution metadata so a release only bumps one place.
    __version__ = version("mini-pi")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]

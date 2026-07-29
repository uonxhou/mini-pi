"""
Configuration file handling for mini-pi.

Reads from ~/.mini-pi/config.json (global config).
Project-level .mini-pi/config.json is planned for Phase 7.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def get_config_path() -> Path:
    """Return the path to the global config file."""
    return Path.home() / ".mini-pi" / "config.json"


def load_config() -> dict:
    """
    Load configuration from the global config file.

    Returns an empty dict if the file does not exist.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Save configuration to the global config file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n")

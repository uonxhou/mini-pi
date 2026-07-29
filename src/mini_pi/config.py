"""
Configuration file handling for mini-pi.

Follows pi's design:
- auth.json   — API keys per provider, with !command/$VAR interpolation, 0600 perms
- config.json — General settings (model, base_url, etc.)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────────

CONFIG_DIR = Path.home() / ".mini-pi"


def get_config_path() -> Path:
    """Path to general settings config."""
    return CONFIG_DIR / "config.json"


def get_auth_path() -> Path:
    """Path to provider API keys (like pi's auth.json)."""
    return CONFIG_DIR / "auth.json"


# ─── General Config ────────────────────────────────────────────────────────


def load_config() -> dict:
    """Load general settings from config.json. Returns empty dict if not found."""
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Save general settings to config.json."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


# ─── Auth (API Keys) ───────────────────────────────────────────────────────


def load_auth() -> dict:
    """
    Load API keys from auth.json.

    Returns a dict keyed by provider name:
        {"deepseek": {"type": "api_key", "key": "sk-..."}}
    """
    path = get_auth_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_auth(data: dict) -> None:
    """
    Save API keys to auth.json with 0600 permissions (user read/write only).

    Mirrors pi's behaviour of restricting access to credential files.
    """
    path = get_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write with restricted permissions
    content = json.dumps(data, indent=2) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)


# ─── Key Resolution ────────────────────────────────────────────────────────

# Matches "$VARNAME" or "${VARNAME}" patterns (not "$$" escaped)
_ENV_INTERPOLATION_RE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")


def resolve_key_value(raw: str) -> str:
    """
    Resolve a key value from auth.json.

    pi-compatible syntax:
        "!command"      — execute command, use stdout (cached per process lifetime)
        "$VAR" / "${VAR}" — interpolate environment variable
        "$$"            — literal "$"
        "$!"            — literal "!"
        "sk-..."        — literal value (plain text)

    Environment interpolation works inside larger strings:
        "prefix_${KEY}_suffix"
    """
    if not raw:
        return raw

    # ── Command execution: value starts with "!" ──
    if raw.startswith("!"):
        cmd = raw[1:]
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {result.returncode}): {cmd}\n{result.stderr.strip()}"
            )
        return result.stdout.strip()

    # ── "$!" escape → literal "!" (before interpolation) ──
    if raw.startswith("$!"):
        return raw[1:]  # strip the "$"

    # ── "$$" escape → placeholder (protect from interpolation) ──
    DOLLAR_PLACEHOLDER = "\x00DOLLAR\x00"
    result = raw.replace("$$", DOLLAR_PLACEHOLDER)

    # ── Environment interpolation: $VAR or ${VAR} ──
    def _replace(m: re.Match) -> str:
        var_name = m.group(1) or m.group(2)
        return os.environ.get(var_name, "")

    result = _ENV_INTERPOLATION_RE.sub(_replace, result)

    # ── Restore literal "$" ──
    result = result.replace(DOLLAR_PLACEHOLDER, "$")

    return result


def resolve_api_key(
    provider: str,
    auth: dict | None = None,
) -> str | None:
    """
    Resolve API key for a provider.

    Priority (mirrors pi):
        1. auth.json entry for the provider
        2. Environment variable ({PROVIDER}_API_KEY, e.g. DEEPSEEK_API_KEY)
        3. None (caller should raise a friendly error)

    The env var name is derived from provider: f"{provider.upper()}_API_KEY".
    """
    if auth is None:
        auth = load_auth()

    # 1. auth.json
    entry = auth.get(provider)
    if entry and isinstance(entry, dict) and "key" in entry:
        try:
            return resolve_key_value(entry["key"])
        except (RuntimeError, KeyError) as e:
            raise RuntimeError(
                f"Failed to resolve API key for provider '{provider}' "
                f"from auth.json: {e}"
            ) from e

    # 2. Environment variable: {PROVIDER}_API_KEY
    env_var = f"{provider.upper()}_API_KEY"
    env_val = os.environ.get(env_var)
    if env_val:
        return env_val

    return None


# ─── Provider Detection ────────────────────────────────────────────────────


def detect_provider(model: str, base_url: str | None = None) -> str:
    """
    Detect which provider to use based on model name and base URL.

    Returns a provider key that matches auth.json entries.
    """
    model_lower = model.lower()
    base_url_lower = (base_url or "").lower()

    # base_url is the strongest signal
    if "deepseek" in base_url_lower:
        return "deepseek"
    if "openai" in base_url_lower:
        return "openai"
    if "minimaxi" in base_url_lower or "minimax" in base_url_lower:
        return "minimax"

    # model name heuristics
    if model_lower.startswith("deepseek"):
        return "deepseek"
    if model_lower.startswith("gpt") or model_lower.startswith("o1") or model_lower.startswith("o3"):
        return "openai"
    if model_lower.startswith("minimax"):
        return "minimax"

    # default
    return "deepseek"




"""
CLI entry point for mini-pi.

Usage:
    mini-pi "Your prompt here"

    # Or run interactively:
    mini-pi --interactive

Environment:
    DEEPSEEK_API_KEY    Required. Your DeepSeek API key.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Imported for its side effect only: importing `readline` transparently upgrades
# the built-in input() with line editing and history. We never call it directly.
#
# `readline` is a Unix-only stdlib module, absent on Windows. There we depend on
# pyreadline3 (declared in pyproject.toml), which registers itself under the same
# name. The guard keeps mini-pi importable even without it — one-shot mode needs
# no line editing at all, so degrading is strictly better than crashing at import.
try:
    import readline  # noqa: F401
except ImportError:
    pass

from mini_pi import __version__
from mini_pi.agent.loop import AgentLoop
from mini_pi.config import get_auth_path, get_config_path, load_config
from mini_pi.llm.client import LLMClient
from mini_pi.tools.base import ToolRegistry
from mini_pi.tools.bash import BashTool
from mini_pi.tools.edit import EditTool
from mini_pi.tools.read import ReadTool
from mini_pi.tools.write import WriteTool

# ─── Color helpers ─────────────────────────────────────────────────────────


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    BLUE = "\033[34m"


def print_banner():
    """Print mini-pi startup banner."""
    width = 29
    c, b, r = Colors.CYAN, Colors.BOLD, Colors.RESET
    lines = [(f"mini-pi v{__version__}", True), ("A minimal coding agent", False)]

    print(f"{c}{b}╭{'─' * width}╮{r}")
    for text, bold in lines:
        # Centre on the raw text, then style — padding must not count ANSI codes.
        pad = max(0, width - len(text))
        left, right = pad // 2, pad - pad // 2
        styled = f"{b}{text}{r}" if bold else text
        print(f"{c}{b}│{r}{' ' * left}{styled}{' ' * right}{c}{b}│{r}")
    print(f"{c}{b}╰{'─' * width}╯{r}")
    print()


def print_tool_event(event_type: str, data: dict) -> None:
    """Pretty-print a tool-related event."""
    name = data.get("name", "unknown")
    if event_type == "tool_call":
        args = data.get("arguments", {})
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
        print(f"\n{Colors.BLUE}🔧 {name}({args_str}){Colors.RESET}")
    elif event_type == "tool_start":
        print(f"{Colors.DIM}   Running...{Colors.RESET}", end="\r")
    elif event_type == "tool_result":
        content = data.get("content", "")
        is_error = data.get("is_error", False)
        if is_error:
            print(f"{Colors.RED}   ✗ Error{Colors.RESET}")
            # Print first few lines
            first_line = content.split("\n")[0][:120]
            print(f"{Colors.RED}   {first_line}{Colors.RESET}")
        else:
            # Show first line of output
            first_line = content.split("\n")[0][:120]
            print(f"{Colors.GREEN}   ✓ {first_line}{Colors.RESET}")


async def run_prompt(prompt: str, model: str, base_url: str | None, cwd: str, api_key: str | None = None) -> None:
    """Run a single prompt and stream the response."""
    # Setup
    client = LLMClient(model=model, base_url=base_url, api_key=api_key)
    tools = ToolRegistry(
        [
            ReadTool(cwd=cwd),
            BashTool(cwd=cwd),
            WriteTool(cwd=cwd),
            EditTool(cwd=cwd),
        ]
    )
    agent = AgentLoop(client, tools)

    print(f"{Colors.DIM}Model: {model}{Colors.RESET}")
    print(f"{Colors.DIM}Tools: {', '.join(tools.get_names())}{Colors.RESET}")
    print(f"{Colors.DIM}CWD: {cwd}{Colors.RESET}")
    print()

    # Run
    print(f"{Colors.BOLD}{Colors.YELLOW}User:{Colors.RESET} {prompt}")
    print()
    print(f"{Colors.BOLD}{Colors.GREEN}Assistant:{Colors.RESET}")

    thinking_started = False

    try:
        async for event in agent.run(prompt):
            if event.type == "text_delta":
                sys.stdout.write(event.data)
                sys.stdout.flush()

            elif event.type == "thinking_delta":
                # Reasoning text (DeepSeek-R1 / reasoner). Streamed live, dimmed.
                if not thinking_started:
                    sys.stdout.write(f"{Colors.DIM}{Colors.CYAN}💭 ")
                    thinking_started = True
                sys.stdout.write(f"{event.data}{Colors.RESET}")
                sys.stdout.flush()

            elif event.type == "tool_call":
                print_tool_event("tool_call", event.data)

            elif event.type == "tool_result":
                print_tool_event("tool_result", event.data)

            elif event.type == "agent_done":
                print()
                print()
                print(f"{Colors.DIM}{agent.get_usage_summary()}{Colors.RESET}")

            elif event.type == "error":
                print(f"\n{Colors.RED}Error: {event.data}{Colors.RESET}")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Interrupted.{Colors.RESET}")


async def run_interactive(model: str, base_url: str | None, cwd: str, api_key: str | None = None) -> None:
    """Run an interactive session with multi-turn conversation."""
    client = LLMClient(model=model, base_url=base_url, api_key=api_key)
    tools = ToolRegistry(
        [
            ReadTool(cwd=cwd),
            BashTool(cwd=cwd),
            WriteTool(cwd=cwd),
            EditTool(cwd=cwd),
        ]
    )
    agent = AgentLoop(client, tools)

    print_banner()
    print(
        f"{Colors.DIM}Model: {client.model} | Base: {client._client.base_url} | Tools: {', '.join(tools.get_names())}{Colors.RESET}"
    )
    print(
        f"{Colors.DIM}Type 'exit' or Ctrl+C to quit, '!cmd' to run bash, '/help' for more{Colors.RESET}"
    )
    print()

    while True:
        try:
            # Read user input
            prompt = input(f"{Colors.BOLD}{Colors.YELLOW}▸{Colors.RESET} ").strip()

            if not prompt:
                continue

            if prompt.lower() == "exit" or prompt.lower() == "/quit":
                print(f"{Colors.DIM}Goodbye!{Colors.RESET}")
                break

            if prompt == "/help":
                print_help()
                continue

            if prompt == "/config":
                print_config_info(client)
                continue

            if prompt == "/usage":
                print(f"{Colors.DIM}{agent.get_usage_summary()}{Colors.RESET}")
                continue

            if prompt == "/clear":
                agent.messages = []
                agent.turns = 0
                agent.total_usage = {"input_tokens": 0, "output_tokens": 0}
                print(f"{Colors.DIM}Conversation cleared.{Colors.RESET}")
                continue

            # Handle !bash commands
            if prompt.startswith("!"):
                cmd = prompt[1:].strip()
                if not cmd:
                    continue
                print(f"{Colors.DIM}Running: {cmd}{Colors.RESET}")
                result = await tools.execute("bash", "cli", command=cmd)
                print(result.content)
                continue

            print()
            print(f"{Colors.BOLD}{Colors.GREEN}Assistant:{Colors.RESET}")

            thinking_started = False

            async for event in agent.run(prompt):
                if event.type == "text_delta":
                    sys.stdout.write(event.data)
                    sys.stdout.flush()

                elif event.type == "thinking_delta":
                    # Reasoning text (DeepSeek-R1 / reasoner). Streamed live, dimmed.
                    if not thinking_started:
                        sys.stdout.write(f"{Colors.DIM}{Colors.CYAN}💭 ")
                        thinking_started = True
                    sys.stdout.write(f"{event.data}{Colors.RESET}")
                    sys.stdout.flush()

                elif event.type == "tool_call":
                    print_tool_event("tool_call", event.data)

                elif event.type == "tool_result":
                    print_tool_event("tool_result", event.data)

                elif event.type == "agent_done":
                    print()
                    print()

                elif event.type == "error":
                    print(f"\n{Colors.RED}Error: {event.data}{Colors.RESET}")

        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Interrupted.{Colors.RESET}")
            # Double Ctrl+C → exit
            try:
                input(f"{Colors.DIM}Press Enter to continue or Ctrl+C again to quit...{Colors.RESET}")
            except (KeyboardInterrupt, EOFError):
                print(f"\n{Colors.DIM}Goodbye!{Colors.RESET}")
                break
        except EOFError:
            print(f"\n{Colors.DIM}Goodbye!{Colors.RESET}")
            break


def print_help():
    """Print interactive mode help."""
    print(f"""
{Colors.BOLD}Commands:{Colors.RESET}
  {Colors.CYAN}exit, /quit{Colors.RESET}     Quit mini-pi
  {Colors.CYAN}/help{Colors.RESET}            Show this help
  {Colors.CYAN}/config{Colors.RESET}          Show current configuration
  {Colors.CYAN}/usage{Colors.RESET}           Show token usage
  {Colors.CYAN}/clear{Colors.RESET}           Clear conversation history
  {Colors.CYAN}!command{Colors.RESET}         Run a bash command directly

{Colors.BOLD}Tips:{Colors.RESET}
  • Ask me to read files, edit code, or run commands
  • I can see your current directory: {os.getcwd()}
  • Config file: {get_config_path()}
  • Use Ctrl+C to interrupt
""")


def print_setup_guide():
    """Print a comprehensive setup and configuration guide."""
    auth_path = get_auth_path()
    config_path = get_config_path()

    print(f"""
{Colors.BOLD}{'=' * 60}{Colors.RESET}
{Colors.BOLD}  mini-pi Setup Guide{Colors.RESET}
{Colors.BOLD}{'=' * 60}{Colors.RESET}

{Colors.BOLD}Step 1 — Get an API Key{Colors.RESET}
  {Colors.DIM}DeepSeek:{Colors.RESET}  https://platform.deepseek.com/api_keys
  {Colors.DIM}OpenAI:{Colors.RESET}    https://platform.openai.com/api-keys

{Colors.BOLD}Step 2 — Configure (pick one){Colors.RESET}
""")

    # Option A: env var
    print(f"""
  {Colors.CYAN}▸ Option A: Environment variable (quickest){Colors.RESET}
    Add to your ~/.zshrc or ~/.bashrc:

      {Colors.GREEN}export DEEPSEEK_API_KEY=sk-...{Colors.RESET}

    Then restart your terminal or run: {Colors.GREEN}source ~/.zshrc{Colors.RESET}
""")

    # Option B: auth.json
    print(f"""
  {Colors.CYAN}▸ Option B: auth.json (pi-style, recommended){Colors.RESET}
    Create {auth_path}:

      {Colors.GREEN}mkdir -p {auth_path.parent}
    cat > {auth_path} << 'EOF'
    {{
      "deepseek": {{"type": "api_key", "key": "sk-..."}}
    }}
    EOF
    chmod 600 {auth_path}{Colors.RESET}

    Or if you use a password manager:
      {Colors.DIM}"key": "!op read op://vault/deepseek/api-key"{Colors.RESET}
""")

    # Option C: CLI flag
    print(f"""
  {Colors.CYAN}▸ Option C: CLI flag (one-off){Colors.RESET}
      {Colors.GREEN}mini-pi -k sk-... "your prompt"{Colors.RESET}
""")

    # Advanced
    print(f"""
{Colors.BOLD}Advanced{Colors.RESET}
  {Colors.DIM}Config file:{Colors.RESET}  {config_path}
    Model and base URL defaults:
      {{"model": "deepseek-reasoner", "base_url": "https://api.deepseek.com"}}

  {Colors.DIM}Multiple providers in auth.json:{Colors.RESET}
    {{
      "deepseek": {{"type": "api_key", "key": "sk-..."}},
      "openai":   {{"type": "api_key", "key": "sk-..."}}
    }}

  {Colors.DIM}Switch provider on the fly:{Colors.RESET}
    {Colors.GREEN}mini-pi -m gpt-4o -b https://api.openai.com/v1{Colors.RESET}

  {Colors.DIM}Key resolution priority:{Colors.RESET}
    {Colors.CYAN}CLI --api-key  >  auth.json  >  environment variable{Colors.RESET}

{Colors.BOLD}{'=' * 60}{Colors.RESET}
""")


def print_config_info(client: LLMClient):
    """Print current configuration (masking sensitive values)."""
    from mini_pi.config import load_auth

    config = load_config()
    auth = load_auth()
    provider = config.get("provider") or "deepseek"

    # Mask API key from auth.json or env
    auth_entry = auth.get(provider, {})
    key_source = "not set"
    if auth_entry.get("key"):
        raw = auth_entry["key"]
        if len(raw) > 14:
            key_source = raw[:10] + "..." + raw[-4:]
        else:
            key_source = "***"
        key_source += " (auth.json)"
    elif os.environ.get("DEEPSEEK_API_KEY"):
        raw = os.environ["DEEPSEEK_API_KEY"]
        if len(raw) > 14:
            key_source = raw[:10] + "..." + raw[-4:]
        else:
            key_source = "***"
        key_source += " (env)"

    print(f"""
{Colors.BOLD}Configuration:{Colors.RESET}
  {Colors.CYAN}Auth file:{Colors.RESET}   {get_auth_path()}
  {Colors.CYAN}Config file:{Colors.RESET}  {get_config_path()}
  {Colors.CYAN}Provider:{Colors.RESET}     {provider}
  {Colors.CYAN}Model:{Colors.RESET}        {client.model}
  {Colors.CYAN}Base URL:{Colors.RESET}     {client._client.base_url}
  {Colors.CYAN}API Key:{Colors.RESET}      {key_source}
""")


def main():
    parser = argparse.ArgumentParser(
        description="mini-pi: A minimal AI coding agent",
        epilog=(
            "Configuration files:\n"
            f"  Auth:   {get_auth_path()}\n"
            f"  Config: {get_config_path()}\n"
            "\n"
            "Quick start (no config needed):\n"
            "  export DEEPSEEK_API_KEY=sk-...\n"
            "  mini-pi \"What files are here?\"\n"
            "  mini-pi -i  # interactive mode"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the agent",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run in interactive mode (multi-turn conversation)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=None,
        help="Model to use (default: deepseek-v4-pro)",
    )
    parser.add_argument(
        "-b",
        "--base-url",
        default=None,
        help="API base URL for OpenAI-compatible providers. Default: https://api.deepseek.com",
    )
    parser.add_argument(
        "-k",
        "--api-key",
        default=None,
        help="API key (overrides auth.json and environment)",
    )
    parser.add_argument(
        "-c",
        "--cwd",
        default=os.getcwd(),
        help="Working directory (default: current directory)",
    )

    args = parser.parse_args()

    # Load config for defaults
    config = load_config()

    # Resolve model: CLI arg > env var > config file
    model = args.model or os.environ.get("MINI_PI_MODEL") or config.get("model")
    base_url = args.base_url or None
    api_key = args.api_key or None

    # If model or base_url is missing, show setup guide
    if not model:
        print()
        print(
            f"{Colors.YELLOW}{'=' * 60}{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}  No model configured.{Colors.RESET}"
        )
        print()
        print(
            f"  Configure {Colors.CYAN}{get_config_path()}{Colors.RESET} with your model and base URL:"
        )
        print()
        print(f"  {Colors.GREEN}{{{Colors.RESET}")
        print(f"    {Colors.GREEN}\"model\": \"your-model-name\",{Colors.RESET}")
        print(f"    {Colors.GREEN}\"base_url\": \"https://api.example.com/v1\"{Colors.RESET}")
        print(f"  {Colors.GREEN}}}{Colors.RESET}")
        print()
        print(
            f"  Or set via: {Colors.CYAN}-m{Colors.RESET} flag, "
            f"{Colors.CYAN}MINI_PI_MODEL{Colors.RESET} env var"
        )
        print(
            f"{Colors.YELLOW}{'=' * 60}{Colors.RESET}"
        )
        print()
        sys.exit(1)

    if not (config.get("base_url") or args.base_url):
        print()
        print(
            f"{Colors.YELLOW}│  No base_url in config. Add it to {get_config_path()}{Colors.RESET}"
        )
        print(
            f"{Colors.DIM}│  Or pass --base-url / -b flag{Colors.RESET}"
        )
        print()

    try:
        if args.interactive:
            asyncio.run(run_interactive(model, base_url, args.cwd, api_key))
        elif args.prompt:
            prompt = " ".join(args.prompt)
            asyncio.run(run_prompt(prompt, model, base_url, args.cwd, api_key))
        else:
            # No prompt and not interactive: run interactive by default
            asyncio.run(run_interactive(model, base_url, args.cwd, api_key))
    except KeyboardInterrupt:
        print()
        sys.exit(0)
    except ValueError as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        print()
        print(
            f"{Colors.DIM}Run {Colors.CYAN}mini-pi --help{Colors.DIM} for quick start instructions.{Colors.RESET}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

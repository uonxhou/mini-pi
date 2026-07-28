"""
CLI entry point for mini-pi.

Usage:
    mini-pi "Your prompt here"

    # Or run interactively:
    mini-pi --interactive

Environment:
    ANTHROPIC_API_KEY    Required. Your Anthropic API key.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mini_pi.agent.loop import AgentLoop
from mini_pi.config import get_config_path, load_config
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
    print(f"{Colors.CYAN}{Colors.BOLD}╭─────────────────────────────╮{Colors.RESET}")
    print(
        f"{Colors.CYAN}{Colors.BOLD}│{Colors.RESET}      {Colors.BOLD}mini-pi v0.1.0{Colors.RESET}       {Colors.CYAN}{Colors.BOLD}│{Colors.RESET}"
    )
    print(
        f"{Colors.CYAN}{Colors.BOLD}│{Colors.RESET}  A minimal coding agent   {Colors.CYAN}{Colors.BOLD}│{Colors.RESET}"
    )
    print(f"{Colors.CYAN}{Colors.BOLD}╰─────────────────────────────╯{Colors.RESET}")
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


async def run_prompt(prompt: str, model: str, base_url: str | None, cwd: str) -> None:
    """Run a single prompt and stream the response."""
    # Setup
    client = LLMClient(model=model, base_url=base_url)
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

    try:
        async for event in agent.run(prompt):
            if event.type == "text_delta":
                sys.stdout.write(event.data)
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


async def run_interactive(model: str, base_url: str | None, cwd: str) -> None:
    """Run an interactive session with multi-turn conversation."""
    client = LLMClient(model=model, base_url=base_url)
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
        f"{Colors.DIM}Model: {model} | Tools: {', '.join(tools.get_names())}{Colors.RESET}"
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

            async for event in agent.run(prompt):
                if event.type == "text_delta":
                    sys.stdout.write(event.data)
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
            print(f"\n{Colors.YELLOW}Interrupted. Type 'exit' to quit.{Colors.RESET}")
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


def print_config_info(client: LLMClient):
    """Print current configuration (masking sensitive values)."""
    config = load_config()
    api_key = config.get("api_key", "")
    masked_key = api_key[:10] + "..." + api_key[-4:] if len(api_key) > 14 else "***"

    print(f"""
{Colors.BOLD}Configuration:{Colors.RESET}
  {Colors.CYAN}Config file:{Colors.RESET}  {get_config_path()}
  {Colors.CYAN}Model:{Colors.RESET}        {client.model}
  {Colors.CYAN}Base URL:{Colors.RESET}     {os.environ.get('ANTHROPIC_BASE_URL') or config.get('base_url') or 'Anthropic default'}
  {Colors.CYAN}API Key:{Colors.RESET}      {masked_key if api_key else 'from env var' if os.environ.get('ANTHROPIC_API_KEY') else 'not set'}
""")


def main():
    parser = argparse.ArgumentParser(
        description="mini-pi: A minimal AI coding agent",
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
        help="Model to use",
    )
    parser.add_argument(
        "-b",
        "--base-url",
        default=None,
        help="API base URL (e.g. MiniMax endpoint). Default: from config/env or Anthropic's default",
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

    # Resolve model: CLI arg > env var > config file > hardcoded default
    model = args.model or os.environ.get("MINI_PI_MODEL") or config.get("model")
    base_url = args.base_url or os.environ.get("ANTHROPIC_BASE_URL") or config.get("base_url")

    if model is None:
        raise ValueError("Model must be specified")

    if args.interactive:
        asyncio.run(run_interactive(model, base_url, args.cwd))
    elif args.prompt:
        prompt = " ".join(args.prompt)
        asyncio.run(run_prompt(prompt, model, base_url, args.cwd))
    else:
        # No prompt and not interactive: run interactive by default
        asyncio.run(run_interactive(model, base_url, args.cwd))


if __name__ == "__main__":
    main()

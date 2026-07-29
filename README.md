# mini-pi

[![PyPI version](https://img.shields.io/pypi/v/mini-pi.svg)](https://pypi.org/project/mini-pi/)
[![Python](https://img.shields.io/pypi/pyversions/mini-pi.svg)](https://pypi.org/project/mini-pi/)

A minimal AI coding agent, built from scratch for learning how AI coding agents work.

Inspired by [pi](https://github.com/earendil-works/pi).

## Architecture

```
mini-pi/
├── main.py                      # Entry point
├── pyproject.toml                # Project config & dependencies
├── AGENTS.md                     # Project memory (for AI agents)
├── docs/
│   └── ROADMAP.md               # 7-phase development plan
└── src/mini_pi/
    ├── types.py                 # Core type definitions (messages, tools, events)
    ├── llm/
    │   └── client.py            # DeepSeek/OpenAI-compatible LLM client with streaming & tool calling
    ├── tools/
    │   ├── base.py              # Tool base class & registry
    │   ├── read.py              # Read files (text & images)
    │   ├── bash.py              # Execute shell commands
    │   ├── write.py             # Create/overwrite files
    │   └── edit.py              # Precise text replacement editing
    ├── agent/
    │   └── loop.py              # Core agent loop (LLM ↔ tools)
    └── cli.py                   # CLI entry point
```

## Components

### 1. Types (`types.py`)
Core data structures: Content blocks (text, image, thinking, tool_call, tool_result), Messages (User, Assistant, ToolResult), Tool definitions with JSON Schema, Usage tracking.

### 2. LLM Client (`llm/client.py`)
- Uses OpenAI SDK, defaulting to DeepSeek API
- Converts internal message format to OpenAI-compatible format
- Handles tool call streaming (accumulates partial function arguments)
- Tracks token usage

### 3. Tools (`tools/`)
- **read**: Read files (text with offset/limit, images as base64)
- **bash**: Execute shell commands with timeout & output truncation
- **write**: Create/overwrite files (auto-creates parent dirs)
- **edit**: Precise text replacement with validation (no-overlap, uniqueness checks)

### 4. Agent Loop (`agent/loop.py`)
The core agentic pattern:
```
User prompt → LLM (with tools) → Tool calls? → Execute → Repeat
                                → No tool calls? → Done
```

### 5. CLI (`cli.py`)
- Single-prompt mode: `mini-pi "List all Python files"`
- Interactive mode: `mini-pi -i` (multi-turn conversation)
- Bash shortcut: `!ls` to run commands directly

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full development plan across 6 phases.

## Installation

### For users (recommended)

```bash
# Via uv tool (fast, isolated environment)
uv tool install mini-pi

# Or via pipx
pipx install mini-pi

# Or via pip
pip install mini-pi
```

### For development

```bash
git clone https://github.com/YOUR_USERNAME/mini-pi.git
cd mini-pi
uv sync
```

## Setup

```bash
# Set your DeepSeek API key
export DEEPSEEK_API_KEY=sk-...

# Run
mini-pi "What files are in the current directory?"

# Interactive mode
mini-pi -i

# Or use any OpenAI-compatible API
mini-pi -m gpt-4o -b https://api.openai.com/v1
```

## Learning Path

This project implements the core of what makes pi tick:

1. **LLM Client** - How to talk to LLM APIs with tool calling
2. **Agent Loop** - The fundamental agentic pattern
3. **Tools** - File I/O, bash execution, precise editing
4. **Streaming** - Real-time response streaming

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned features across 6 phases.

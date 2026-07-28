# mini-pi

A minimal AI coding agent built from scratch for learning AI agent development.
Reference implementation: [pi](https://github.com/earendil-works/pi) ([monorepo](https://github.com/earendil-works/pi-mono)).

## Project Identity

- **Name**: mini-pi
- **Language**: Python ≥3.10
- **Package manager**: uv
- **Source**: `src/mini_pi/`
- **Entry point**: `main.py` → `mini_pi.cli:main`

## Architecture

```
src/mini_pi/
├── types.py          # Core types: messages, tools, events
├── llm/
│   └── client.py     # Anthropic API client (streaming + tool calling)
├── tools/
│   ├── base.py       # Tool base class + ToolRegistry
│   ├── read.py       # Read files (text + images)
│   ├── bash.py       # Execute shell commands
│   ├── write.py      # Create/overwrite files
│   └── edit.py       # Precise text replacement editing
├── agent/
│   └── loop.py       # Core agent loop (LLM ↔ tools)
└── cli.py            # CLI (single-prompt + interactive mode)
```

## Conventions

- Python async/await throughout (no synchronous LLM calls)
- dataclass-based types, no external schema library
- Tools inherit from `BaseTool` and register via `ToolRegistry`
- Streaming uses async generators yielding `AgentEvent`
- CLI uses `argparse`, colored output via ANSI codes
- Dependencies: `anthropic`, `httpx` (declared in pyproject.toml)

## Key Design Decisions

1. **Anthropic-first**: The initial LLM client targets Anthropic's API. Multi-provider support is planned for Phase 3.
2. **Streaming-first**: The `chat_stream()` method is the primary API; `chat()` is a convenience wrapper.
3. **Tool schemas dual-format**: `ToolDefinition` can produce both Anthropic and OpenAI schema formats (ready for Phase 3).
4. **Edit tool uniqueness**: The `edit` tool validates all oldText matches before applying any changes (matches pi's behavior).
5. **Agent yield events**: The loop yields `AgentEvent` objects to the caller, decoupling streaming from UI.

## Development

```bash
# Install
uv sync

# Run single prompt
uv run mini-pi "List Python files"

# Run interactive
uv run mini-pi -i

# Requires
export ANTHROPIC_API_KEY=sk-ant-...
```

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full 7-phase plan.

```
Phase 1  ✅  Core Agent Loop        (types, LLM, tools, agent loop, CLI)
Phase 2  ⬚  Testing & Test Suite    (pytest, mocks, full coverage)
Phase 3  ⬚  Session Persistence     (JSONL, tree, compaction)
Phase 4  ⬚  Multi-Provider          (OpenAI, retry, error handling)
Phase 5  ⬚  Interactive TUI         (Textual-based terminal UI)
Phase 6  ⬚  Extension System        (event-driven middleware)
Phase 7  ⬚  Advanced Features       (skills, prompts, packages)
```

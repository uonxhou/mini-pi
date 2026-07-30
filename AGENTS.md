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
mini-pi/
├── main.py                # Entry point
├── pyproject.toml          # Project config & dependencies
├── AGENTS.md               # Project memory (this file)
├── README.md               # Human-readable overview
├── docs/
│   └── ROADMAP.md          # 7-phase development plan
└── src/mini_pi/
    ├── types.py            # Core types: messages, tools, events
    ├── config.py            # Config & auth file handling, provider detection
    ├── llm/
    │   └── client.py       # OpenAI-compatible LLM client (streaming + tool calling)
    ├── tools/
    │   ├── base.py         # Tool base class + ToolRegistry
    │   ├── read.py         # Read files (text + images)
    │   ├── bash.py         # Execute shell commands
    │   ├── write.py        # Create/overwrite files
    │   └── edit.py         # Precise text replacement editing
    ├── agent/
    │   └── loop.py         # Core agent loop (LLM ↔ tools)
    └── cli.py              # CLI (single-prompt + interactive mode)
```

## Conventions

- Python async/await throughout (no synchronous LLM calls)
- dataclass-based types, no external schema library
- Tools inherit from `BaseTool` and register via `ToolRegistry`
- Streaming uses async generators yielding `AgentEvent`
- CLI uses `argparse`, colored output via ANSI codes
- Dependencies: `openai`, `httpx` (declared in pyproject.toml)
- **Documentation sync**: When project structure changes (new/renamed/moved files or modules), update the Architecture section in AGENTS.md and README.md accordingly

## Key Design Decisions

1. **OpenAI-compatible first**: The LLM client uses the OpenAI SDK, making it compatible with any OpenAI-compatible provider (DeepSeek, MiniMax, OpenAI, etc.). No hardcoded provider defaults — all settings driven by config files, env vars, or CLI flags.
2. **Streaming-first**: The `chat_stream()` method is the primary -; `chat()` is a convenience wrapper.
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
# API key via auth.json, env var ({PROVIDER}_API_KEY), or --api-key flag
```

## Release Process

When the user says "release", "publish", "发布", "完成新版本发布", or similar:

1. **Update version**: Bump the `version` field in `pyproject.toml` (semantic versioning).
2. **Commit**: `git add -A && git commit -m "release: vX.Y.Z"`
3. **Tag**: `git tag vX.Y.Z`
4. **Push**: `git push && git push --tags`

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

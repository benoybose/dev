# devx-coding-agent

`devx` is a **local-first, approval-gated AI coding agent** distributed as a Python package. It ships with two user interfaces:

- A **Textual TUI** for interactive coding sessions
- A **Typer CLI** for one-shot commands and session management

Under the hood, `devx` uses a **LangGraph supervisor workflow** (planner → coder → tester), approval-gated workspace tools, SQLite-backed session persistence, and supports any OpenAI-compatible or native LLM provider (OpenAI, Anthropic, Google, Azure, LiteLLM, Ollama, and more).

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Quick Start](#quick-start)
7. [CLI Usage](#cli-usage)
8. [TUI Usage](#tui-usage)
9. [Slash Commands](#slash-commands)
10. [Development](#development)
11. [Testing](#testing)
12. [Security](#security)
13. [Roadmap](#roadmap)
14. [Contributing](#contributing)

---

## Features

| Feature | Description |
|---|---|
| **LangGraph supervisor** | Explicit planner → coder → tester state machine with conditional branching, loops, and interrupt/resume |
| **Approval-gated tools** | All file writes and shell commands require explicit user approval by default |
| **Atomic writes & rollback** | Every approved write is atomic, backed up, and recorded with before/after hashes; rollback via `/rollback` |
| **SQLite sessions** | Persistent session state, event history, and checkpoint-compatible run IDs |
| **@ file mentions** | Reference files/directories with `@` syntax; fuzzy completion in TUI |
| **Multi-provider support** | OpenAI, Anthropic, Google, Azure, LiteLLM, Ollama, or any OpenAI-compatible endpoint |
| **Local token optimization** | Optional ONNX INT8 embeddings for semantic cache and context compression (zero API calls) |
| **LangSmith tracing** | Optional tracing integration for debugging agent runs |
| **Cross-platform** | Windows, macOS, Linux support with CI/CD |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Textual TUI │  │  Typer CLI   │  │Session Mgr   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│                 Agentic Harness (Multi-Agent)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        LangGraph State Machine / Supervisor            │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │  │
│  │  │ Planner │ │  Coder  │ │ Tester  │ │  Docs   │    │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│              Token Optimization Layer (Client-Side)          │
│  ┌────────────────────┐  ┌─────────────────────────────┐  │
│  │ Local Embeddings   │  │ Semantic Cache + Context    │  │
│  │ (ONNX INT8)        │  │ Selection (@ file mentions) │  │
│  └────────────────────┘  └─────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Model Abstraction Layer                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  LangChain ChatOpenAI (configurable base_url)         │  │
│  │  → Any OpenAI-compatible endpoint                     │  │
│  │    (LiteLLM / vLLM / Ollama / OpenAI / etc.)          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

- **`src/devx/agents/graph.py`** — LangGraph state graph builder; orchestrates planner, coder, and tester stages with conditional branching
- **`src/devx/harness/tools.py`** — `WorkspaceTools`: read, write, replace, search, `git_diff`, and `run` (shell commands)
- **`src/devx/harness/approval.py`** — `ApprovalManager` gates all mutations (writes, command execution)
- **`src/devx/harness/session.py`** — `SessionStore` (SQLite CRUD + event log)
- **`src/devx/harness/changes.py`** — `ChangeJournal` (atomic writes, backups, rollback support)
- **`src/devx/tui/app.py`** — `DevxTUI` (Textual app)
- **`src/devx/cli/app.py`** — Typer CLI entrypoint

---

## Requirements

- **Python** >= 3.11
- **pip** (for installation)
- An LLM provider API key (or local Ollama/LiteLLM endpoint)

---

## Installation

### From source (recommended for development)

```bash
pip install -e ".[agent,tui,cli]"
```

### Optional extras

```bash
# All optional dependencies
pip install -e ".[all]"

# Or pick specific extras:
pip install -e ".[agent,anthropic,google,embeddings,tracing,dev]"
```

| Extra | Packages | Purpose |
|---|---|---|
| `agent` | langchain, langgraph, langgraph-checkpoint-sqlite, langchain-openai | Core agent runtime |
| `tui` | textual | Textual TUI |
| `cli` | typer | Typer CLI |
| `openai` | langchain-openai | OpenAI provider |
| `anthropic` | langchain-anthropic | Anthropic provider |
| `google` | langchain-google-genai | Google provider |
| `azure` | langchain-openai | Azure OpenAI provider |
| `embeddings` | numpy, onnxruntime, transformers, sentence-transformers | Local ONNX embeddings |
| `tracing` | langsmith | LangSmith tracing |
| `dev` | pytest, pytest-cov, ruff, pyright | Development tools |
| `all` | all of the above | Full installation |

---

## Configuration

`devx` loads configuration from **`~/.devx/config.env`** (or legacy `~/.dev/config.env`) **and** environment variables. The precedence order is: environment variables > `config.env` > built-in defaults.

### Environment Variables

Both `DEVX_*` and legacy `DEV_*` variable names are supported, with `DEVX_*` taking precedence.

| Variable | Default | Description |
|---|---|---|
| `DEVX_BASE_URL` | `http://localhost:4000/v1` | OpenAI-compatible API endpoint |
| `DEVX_API_KEY` | `sk-placeholder` | API key for the LLM provider |
| `DEVX_MODEL` | `gpt-4o` | Model name to use |
| `DEVX_PROVIDER` | `openai` | Provider: `openai`, `anthropic`, `google`, `azure` |
| `DEVX_WORKSPACE` | `cwd` (current working directory) | Workspace root directory |
| `DEVX_SESSION_DB` | `~/.devx/sessions.db` | SQLite session database path |
| `DEVX_CACHE_DB` | `~/.devx/cache.db` | Semantic cache database path |
| `DEVX_APPROVAL_REQUIRED` | `true` | Require approval for file writes and commands |
| `DEVX_MAX_ITERATIONS` | `8` | Maximum agent loop iterations per run |
| `DEVX_MAX_TOOL_CALLS` | `40` | Maximum tool calls per run |
| `DEVX_COMMAND_TIMEOUT` | `120` | Shell command timeout in seconds |
| `DEVX_TEST_COMMAND` | `""` (auto-detect) | Custom test command for tester agent |
| `DEVX_MAX_FILE_BYTES` | `1000000` | Maximum file size to read (bytes) |
| `DEVX_EMBEDDINGS_ENABLED` | `false` | Enable local ONNX embeddings for token optimization |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith tracing |

### Example `~/.devx/config.env`

```env
DEVX_BASE_URL=https://api.openai.com/v1
DEVX_API_KEY=sk-...
DEVX_MODEL=gpt-4o
DEVX_PROVIDER=openai
DEVX_WORKSPACE=C:/Projects/my-project
DEVX_APPROVAL_REQUIRED=true
DEVX_TEST_COMMAND=pytest
DEVX_EMBEDDINGS_ENABLED=true
```

> **Note:** Quoted values are supported in `config.env`.

---

## Quick Start

1. **Install:**
   ```bash
   pip install -e ".[agent,tui,cli]"
   ```

2. **Configure your provider:**
   Set `DEVX_BASE_URL`, `DEVX_API_KEY`, and `DEVX_MODEL`, or create `~/.devx/config.env`.

3. **Run the doctor check:**
   ```bash
   devx doctor
   ```

4. **Start coding:**
   ```bash
   # Interactive TUI
   devx tui

   # One-shot CLI
   devx ask "inspect @src/app.py"
   ```

---

## CLI Usage

The `devx` CLI exposes the following commands:

### `devx ask`

Run a single agent task.

```bash
devx ask "explain @src/main.py"
devx ask --session my-project "fix the bug in @src/utils.py"
devx ask --approve-all "run tests and fix failures"   # trusted workspaces only
```

| Option | Description |
|---|---|
| `--session NAME` | Resume or create a named session |
| `--approve-all` | Auto-approve all writes and commands (use only in trusted, isolated workspaces) |

### `devx tui`

Launch the interactive Textual TUI.

```bash
devx tui
```

### `devx doctor`

Run a diagnostic check to verify configuration, provider connectivity, and dependencies.

```bash
devx doctor
```

### `devx sessions`

List all sessions.

```bash
devx sessions
```

### `devx session list`

Alias for `devx sessions`.

### `devx session events <ID>`

Show event history for a specific session.

```bash
devx session events abc123
```

### `devx session delete <ID>`

Delete a session and its events.

```bash
devx session delete abc123
```

---

## TUI Usage

Launch the TUI with `devx tui`.

### Features

- **Chat interface** — Conversational interaction with the coding agent
- **@ file mentions** — Type `@` to reference files or directories; fuzzy completion is provided
- **Slash commands** — Control sessions and agent behavior (see below)
- **Approval prompts** — Inline approval requests for writes and commands
- **Session management** — Resume, create, and delete sessions from the sidebar
- **Diff view** — Inspect before/after diffs for every approved write

---

## Slash Commands

| Command | Description |
|---|---|
| `/rollback` | Roll back the last approved file change (only if the file has not been modified after the run) |
| `/approve` | Approve a pending write or command |
| `/reject` | Reject a pending write or command |
| `/clear` | Clear the current conversation |
| `/help` | Show help for available commands |

> **Note:** The command set is minimal by design. Additional commands may be added in future releases.

---

## Supported Providers

`devx` supports any OpenAI-compatible endpoint or native provider:

| Provider | Configuration |
|---|---|
| **OpenAI** | `DEVX_PROVIDER=openai`, `DEVX_BASE_URL=https://api.openai.com/v1` |
| **Anthropic** | `DEVX_PROVIDER=anthropic`, `DEVX_BASE_URL=https://api.anthropic.com` |
| **Google** | `DEVX_PROVIDER=google` |
| **Azure OpenAI** | `DEVX_PROVIDER=azure`, `DEVX_BASE_URL=https://<resource>.openai.azure.com` |
| **LiteLLM** | `DEVX_PROVIDER=openai`, `DEVX_BASE_URL=http://localhost:4000/v1` |
| **Ollama** | `DEVX_PROVIDER=openai`, `DEVX_BASE_URL=http://localhost:11434/v1` |
| **vLLM / any compatible** | `DEVX_PROVIDER=openai`, `DEVX_BASE_URL=<your-endpoint>` |

Tool calling support is required for the agent harness to function correctly.

---

## Security

By default, `devx` is designed with a security-first approach:

- **Approval required** — All file writes and shell commands require explicit user approval (`DEVX_APPROVAL_REQUIRED=true` by default)
- **Workspace sandboxing** — All file operations are resolved relative to the configured workspace; paths outside the workspace are rejected
- **Atomic writes** — File writes are atomic with automatic backups and before/after hashes
- **No auto-commits** — The agent never commits Git changes automatically; inspect diffs and commit yourself
- **Bounded shell execution** — Commands run with `shell=False`, bounded output, configurable timeouts, and process cleanup
- **Secret redaction** — API keys and tokens are redacted from logs and traces
- **No auto-approve** — `--approve-all` is explicitly opt-in and intended only for trusted, isolated workspaces

For more details, see [SECURITY.md](SECURITY.md).

---

## Development

### Clone the repository

```bash
git clone https://github.com/your-org/devx-coding-agent.git
cd devx
```

### Install in development mode

```bash
pip install -e ".[agent,tui,cli,dev]"
```

### Run the TUI

```bash
devx tui
```

### Run the CLI

```bash
devx ask "hello world"
```

---

## Testing

Run the test suite with pytest:

```bash
pytest
```

The test configuration is defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers"
pythonpath = ["src", "."]
```

### Lint and format

```bash
ruff check src/
```

### Type check

```bash
pyright
```

### CI/CD

The project uses GitHub Actions for continuous integration and automated PyPI releases:

- `.github/workflows/ci.yml` — Runs tests, lint, and type checks on every push and pull request
- `.github/workflows/release.yml` — Automates PyPI releases on version tags

---

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for the full roadmap.

Current priorities:

- Multi-file refactoring support
- RAG-based codebase context
- Extension system (custom tools, custom agents)
- Web-based dashboard for session history and diffs

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure tests pass (`pytest`) and linting passes (`ruff check src/`)
5. Submit a pull request

---

## License

MIT

---

## Acknowledgments

Built with [LangChain](https://python.langchain.com/), [LangGraph](https://langchain-ai.github.io/langgraph/), [Textual](https://textual.textualize.io/), and [Typer](https://typer.tiangolo.com/).

# dev-coding-agent

`dev` is a **local-first, approval-gated AI coding agent** distributed as a Python package. It ships with two user interfaces:

- A **Textual TUI** for interactive coding sessions
- A **Typer CLI** for one-shot commands and session management

Under the hood, `dev` uses a **LangGraph supervisor workflow** (planner → coder → tester), approval-gated workspace tools, SQLite-backed session persistence, and supports any OpenAI-compatible or native LLM provider (OpenAI, Anthropic, Google, Azure, LiteLLM, Ollama, and more).

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

- **`src/dev/agents/graph.py`** — LangGraph state graph builder; orchestrates planner, coder, and tester stages with conditional branching
- **`src/dev/harness/tools.py`** — `WorkspaceTools`: read, write, replace, search, `git_diff`, and `run` (shell commands)
- **`src/dev/harness/approval.py`** — `ApprovalManager` gates all mutations (writes, command execution)
- **`src/dev/harness/session.py`** — `SessionStore` (SQLite CRUD + event log)
- **`src/dev/harness/changes.py`** — `ChangeJournal` (atomic writes, backups, rollback support)
- **`src/dev/tui/app.py`** — `DevTUI` (Textual app)
- **`src/dev/cli/app.py`** — Typer CLI entrypoint

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
| `embeddings` | numpy, onnxruntime, transformers, sentence-transformers | Optional local embeddings |
| `tracing` | langsmith | LangSmith tracing |
| `dev` | pytest, pytest-cov, ruff, pyright | Development tools |
| `all` | all of the above | Full installation |

---

## Configuration

`dev` loads configuration from **`~/.dev/config.env`** (if present) **and** environment variables. The precedence order is: environment variables > `config.env` > built-in defaults.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DEV_BASE_URL` | `http://localhost:4000/v1` | OpenAI-compatible API endpoint |
| `DEV_API_KEY` | `sk-placeholder` | API key for the LLM provider |
| `DEV_MODEL` | `gpt-4o` | Model name to use |
| `DEV_PROVIDER` | `openai` | Provider: `openai`, `anthropic`, `google`, `azure` |
| `DEV_WORKSPACE` | `cwd` (current working directory) | Workspace root directory |
| `DEV_SESSION_DB` | `~/.dev/sessions.db` | SQLite session database path |
| `DEV_CACHE_DB` | `~/.dev/cache.db` | Semantic cache database path |
| `DEV_APPROVAL_REQUIRED` | `true` | Require approval for file writes and commands |
| `DEV_MAX_ITERATIONS` | `8` | Maximum agent loop iterations per run |
| `DEV_MAX_TOOL_CALLS` | `40` | Maximum tool calls per run |
| `DEV_COMMAND_TIMEOUT` | `120` | Shell command timeout in seconds |
| `DEV_TEST_COMMAND` | `""` (auto-detect) | Custom test command for tester agent |
| `DEV_MAX_FILE_BYTES` | `1000000` | Maximum file size to read (bytes) |
| `DEV_EMBEDDINGS_ENABLED` | `false` | Enable local ONNX embeddings for token optimization |
| `DEV_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model identifier |
| `DEV_EMBEDDING_CACHE_DIR` | `~/.cache/dev/embeddings` | Local embedding model cache directory |
| `DEV_EMBEDDINGS_OFFLINE` | `false` | Prevent embedding model downloads and use cached files only |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith tracing |

### Example `~/.dev/config.env`

```env
DEV_BASE_URL=https://api.openai.com/v1
DEV_API_KEY=sk-...
DEV_MODEL=gpt-4o
DEV_PROVIDER=openai
DEV_WORKSPACE=C:/Projects/my-project
DEV_APPROVAL_REQUIRED=true
DEV_TEST_COMMAND=pytest
DEV_EMBEDDINGS_ENABLED=true
```

> **Note:** Quoted values are supported in `config.env`.

---

## Quick Start

1. **Install:**
   ```bash
   pip install -e ".[agent,tui,cli]"
   ```

2. **Configure your provider:**
   Set `DEV_BASE_URL`, `DEV_API_KEY`, and `DEV_MODEL`, or create `~/.dev/config.env`.

3. **Run the doctor check:**
   ```bash
   dev doctor
   ```

4. **Start coding:**
   ```bash
   # Interactive TUI
   dev tui

   # One-shot CLI
   dev ask "inspect @src/app.py"
   ```

---

## CLI Usage

The `dev` CLI exposes the following commands:

### `dev ask`

Run a single agent task.

```bash
dev ask "explain @src/main.py"
dev ask --session my-project "fix the bug in @src/utils.py"
dev ask --approve-all "run tests and fix failures"   # trusted workspaces only
```

| Option | Description |
|---|---|
| `--session NAME` | Resume or create a named session |
| `--approve-all` | Auto-approve all writes and commands (use only in trusted, isolated workspaces) |

### `dev tui`

Launch the interactive Textual TUI.

```bash
dev tui
```

### `dev doctor`

Run a diagnostic check to verify configuration, provider connectivity, and dependencies.

```bash
dev doctor
```

### `dev sessions`

List all sessions.

```bash
dev sessions
dev session rename local-dev renamed-session
dev session export local-dev ./local-dev-session.json
dev session import ./local-dev-session.json imported-session
```

### `dev session list`

Alias for `dev sessions`.

### `dev session events <ID>`

Show event history for a specific session.

```bash
dev session events abc123
```

### `dev session delete <ID>`

Delete a session and its events.

```bash
dev session delete abc123
```

---

## TUI Usage

Launch the TUI with `dev tui`.

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

`dev` supports any OpenAI-compatible endpoint or native provider:

| Provider | Configuration |
|---|---|
| **OpenAI** | `DEV_PROVIDER=openai`, `DEV_BASE_URL=https://api.openai.com/v1` |
| **Anthropic** | `DEV_PROVIDER=anthropic`, `DEV_BASE_URL=https://api.anthropic.com` |
| **Google** | `DEV_PROVIDER=google` |
| **Azure OpenAI** | `DEV_PROVIDER=azure`, `DEV_BASE_URL=https://<resource>.openai.azure.com` |
| **LiteLLM** | `DEV_PROVIDER=openai`, `DEV_BASE_URL=http://localhost:4000/v1` |
| **Ollama** | `DEV_PROVIDER=openai`, `DEV_BASE_URL=http://localhost:11434/v1` |
| **vLLM / any compatible** | `DEV_PROVIDER=openai`, `DEV_BASE_URL=<your-endpoint>` |

Tool calling support is required for the agent harness to function correctly.

---

## Security

By default, `dev` is designed with a security-first approach:

- **Approval required** — All file writes and shell commands require explicit user approval (`DEV_APPROVAL_REQUIRED=true` by default)
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
git clone https://github.com/your-org/dev-coding-agent.git
cd dev-coding-agent
```

### Install in development mode

```bash
pip install -e ".[agent,tui,cli,dev]"
```

### Run the TUI

```bash
dev tui
```

### Run the CLI

```bash
dev ask "hello world"
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
pythonpath = ["src"]
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

# Cross-Platform CLI Development Guide

This guide explains how to install, run, test, and troubleshoot the `dev`
command while developing this project on Linux, macOS, or Windows.

The project exposes the CLI through the following declaration in
`pyproject.toml`:

```toml
[project.scripts]
dev = "dev.cli.app:main"
```

Installing the project creates a platform-specific launcher named `dev`.
Installing in editable mode means that changes under `src/dev` are used
immediately without rebuilding or reinstalling the package.

## Prerequisites

Install Python 3.11 or newer and Git. Verify both tools before starting.

Linux and macOS:

```bash
python3 --version
git --version
```

Windows PowerShell:

```powershell
py --version
git --version
```

The CI matrix tests Python 3.11, 3.12, and 3.13 on Ubuntu, Windows, and
macOS. Python 3.12 is a good local default because it matches the packaging
workflow.

## Create a development environment

Run these commands from the repository root.

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[agent,tui,cli,dev]"
```

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[agent,tui,cli,dev]"
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[agent,tui,cli,dev]"
```

The extras install the core agent runtime, Textual TUI, Typer CLI, and local
development tools. Use `.[all]` when every optional dependency is required.

## How the `dev` command is created

The editable installation creates a console launcher inside the virtual
environment:

| Platform | Launcher |
|---|---|
| Linux | `.venv/bin/dev` |
| macOS | `.venv/bin/dev` |
| Windows | `.venv\\Scripts\\dev.exe` |

Activating the virtual environment adds that directory to the current shell's
`PATH`. Therefore this resolves to the project launcher:

```text
dev doctor
```

Check the resolved executable with:

Linux and macOS:

```bash
which dev
```

Windows PowerShell:

```powershell
Get-Command dev
where.exe dev
```

The result should point inside the repository's `.venv` directory. The
launcher can also be called directly without activation:

```bash
.venv/bin/dev doctor
```

```powershell
.\.venv\Scripts\dev.exe doctor
```

## Configure a provider

The CLI loads configuration from environment variables and, when present,
`~/.dev/config.env`. Environment variables take precedence.

For an OpenAI-compatible endpoint, configure the current shell as follows.

Linux and macOS:

```bash
export DEV_BASE_URL="https://api.openai.com/v1"
export DEV_API_KEY="your-api-key"
export DEV_MODEL="gpt-4o"
export DEV_PROVIDER="openai"
export DEV_WORKSPACE="$PWD"
export DEV_APPROVAL_REQUIRED="true"
```

Windows PowerShell:

```powershell
$env:DEV_BASE_URL = "https://api.openai.com/v1"
$env:DEV_API_KEY = "your-api-key"
$env:DEV_MODEL = "gpt-4o"
$env:DEV_PROVIDER = "openai"
$env:DEV_WORKSPACE = (Get-Location).Path
$env:DEV_APPROVAL_REQUIRED = "true"
```

For persistent configuration, create `~/.dev/config.env`. On Windows this is
normally `%USERPROFILE%\\.dev\\config.env`.

```env
DEV_BASE_URL=https://api.openai.com/v1
DEV_API_KEY=your-api-key
DEV_MODEL=gpt-4o
DEV_PROVIDER=openai
DEV_APPROVAL_REQUIRED=true
DEV_TEST_COMMAND=pytest
```

Never commit API keys or place them in tracked project files.

## Verify the installation

Run the diagnostic command after configuration:

```text
dev doctor
```

It reports the workspace, provider, model, optional dependency status, and
overall configuration status. Inspect the complete command surface with:

```text
dev --help
```

## Run CLI tasks

Run a one-shot task:

```text
dev ask "inspect @src/dev/cli/app.py"
dev ask "run the tests and explain any failures"
```

The `@path` syntax supplies files or directories from the configured
workspace. Paths outside the workspace are rejected.

Use a named session to preserve conversational state:

```text
dev ask --session local-dev "inspect the project structure"
dev ask --session local-dev "suggest improvements"
dev sessions
dev session events local-dev
```

Use JSON output for scripts or automation:

```text
dev ask --json "summarize the repository"
```

For trusted, isolated workspaces, `--approve-all` automatically approves file
writes and commands:

```text
dev ask --approve-all "run the test suite and fix failures"
```

Only use automatic approval when the workspace and generated changes are
trusted.

## Run the TUI

The Textual user interface is included by the `tui` extra:

```text
dev tui
```

Resume a named session from the TUI when supported by the installed version:

```text
dev tui --session local-dev
```

If the TUI import is unavailable, install the TUI extra:

```bash
python -m pip install -e ".[tui]"
```

## Development and test commands

Run the complete local test suite:

```text
python -m pytest -q
```

Run linting:

```text
python -m ruff check src tests scripts
```

Compile-check the Python sources:

```text
python -m compileall -q src tests scripts
```

Run focused tests while developing:

```text
python -m pytest -q tests/test_core.py
python -m pytest -q tests/test_tui_smoke.py
python -m pytest -q tests/test_version.py
```

The CI workflow additionally runs dependency auditing, provider contract
tests, package building, wheel installation, and the `dev doctor` smoke test.

## Common problems

### `dev` is not recognized

The virtual environment is probably not active, or the editable install did
not complete. Activate the environment and reinstall:

```bash
source .venv/bin/activate
python -m pip install -c constraints.txt -e ".[agent,tui,cli,dev]"
```

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -c constraints.txt -e ".[agent,tui,cli,dev]"
```

### PowerShell blocks activation

If the machine policy permits it, enable locally created scripts for the
current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate the environment again.

### Provider or API errors

Check the active values without printing the secret:

```bash
echo "$DEV_BASE_URL"
echo "$DEV_MODEL"
echo "$DEV_PROVIDER"
```

```powershell
$env:DEV_BASE_URL
$env:DEV_MODEL
$env:DEV_PROVIDER
```

Verify that the selected provider package is installed and that the endpoint
supports the model and tool-calling behavior required by the agent.

### The CLI uses the wrong Python installation

Always invoke pip through the active interpreter:

```text
python -m pip --version
python -c "import sys; print(sys.executable)"
```

Both should point into `.venv`.

### Tests fail because of temporary-directory permissions

Pytest needs a writable temporary directory. On managed systems, configure a
writable temporary location before running tests:

```powershell
$env:TMP = "C:\\path\\to\\writable-temp"
$env:TEMP = $env:TMP
python -m pytest -q
```

Hosted CI runners provide writable temporary directories by default.

## Deactivate or recreate the environment

Deactivate the current environment with:

```text
deactivate
```

To recreate it, remove the `.venv` directory and repeat the setup commands.
Do not remove the project source or `.git` directory.

## Related documentation

- [README](../README.md) — project overview, configuration, and CLI reference
- [Architecture](architecture.md) — runtime and agent design
- [GitFlow](gitflow.md) — branch and semantic-versioning policy

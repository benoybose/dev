# dev

`dev` is a local-first coding agent with a Textual TUI and Typer CLI. It uses a
LangGraph-style supervisor workflow, approval-gated tools, SQLite sessions, and
any supported OpenAI-compatible or native provider.

## Install

```bash
pip install -e ".[agent,tui,cli]"
```

Configure `DEV_BASE_URL`, `DEV_API_KEY`, and `DEV_MODEL` (or use a native
provider configuration). Run `dev doctor`, then `dev tui` or
`dev ask "inspect @src/app.py"`.

Writes and commands require approval by default. The agent never commits Git
changes automatically; inspect the resulting diff and commit yourself.

The CLI supports `dev sessions`, `dev session list`, `dev session events ID`,
and `dev session delete ID`. Use `dev ask --session NAME "..."` to resume a
conversation. Set `DEV_TEST_COMMAND` to enable an approved test-and-repair
loop. `dev ask --approve-all` is intended only for explicitly trusted,
isolated workspaces.

Every approved write is atomic, recorded with before/after hashes, and can be
rolled back from the TUI with `/rollback` when the file has not been modified
after the run.

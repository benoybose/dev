# Changelog

## Unreleased (0.2.0-dev.0)

- Added TUI `/diff`, `/undo`, and `/plan` workflows with bounded approval previews.
- Added CLI `--plan-only`, configurable linting, bounded context selection, and structured cancellation.
- Namespaced semantic-cache entries by provider, model, and embedding model to prevent stale cross-model reuse.
- Added deterministic offline DX benchmarks for output limits, command safety, rollback, and context budgets.
- Added ordered project permissions with `allow`, `ask`, and `deny` effects while preserving workspace and destructive-command safeguards.
- Added bounded local context compaction, a shared tool registry, workspace Python plugins, and stdio MCP tool discovery/calls.
- Expanded regression coverage and CI validation for the new workflows.
- Current validation: 70 tests pass, provider-contract checks pass, offline benchmarks pass, and Ruff/compile/diff checks pass.

## 0.1.0

- Initial local-first coding-agent package.
- LangGraph supervisor workflow with planner, coder, and tester stages.
- Approval-gated workspace tools, atomic writes, diffs, backups, and rollback.
- SQLite sessions, event history, and checkpoint-compatible run IDs.
- Textual TUI and Typer CLI.
- Optional local embeddings and semantic cache.
- Cross-platform CI and package-release workflows.


# `dev` Production Roadmap

## Current status

`dev` is at a production-candidate stage for local validation. The core
package, CLI, TUI, LangGraph supervisor, approval controls, sessions, local
context optimization, testing hooks, packaging, and CI definitions are in
place.

Current local validation:

- 16 automated tests passing.
- Ruff and Python compilation passing.
- Textual pilot tests passing.
- LangChain provider-contract and tool-calling smoke tests passing.
- LangGraph SQLite checkpoint construction passing.
- Wheel build and isolated installation passing.
- Declared dependency audit passing.

## Release 0.1.0 gate

### External validation

- Push the repository to GitHub.
- Run the CI matrix on Windows, Linux, and macOS with Python 3.11–3.13.
- Verify the package job builds, installs, and runs `dev doctor`.
- Configure short-lived staging credentials for supported providers.
- Run live acceptance tests for OpenAI-compatible, Anthropic, Google, and
  Azure configurations where credentials and deployments are available.
- Review CI dependency-audit and security-scan artifacts.
- Resolve platform- or provider-specific failures.

### Release preparation

- Review the final wheel and source distribution contents.
- Confirm version, changelog, README, security policy, and license metadata.
- Create the `v0.1.0` tag.
- Publish through the release workflow.
- Install the published package in a clean environment.
- Verify `dev doctor`, `dev sessions`, `dev ask`, and `dev tui` after install.

## Post-release 0.2.0

### Reliability and workflow quality

- Add richer LangGraph interrupt/resume tests across process restarts.
- Add complete approval-history persistence and approval replay rules.
- Add process-tree and cancellation tests on every supported OS.
- Improve test-framework detection with package-manager and virtual-environment
  awareness.
- Add configurable test selection and per-project test policies.
- Add conflict-resolution UX when files change during an agent run.

### User experience

- Add richer diff previews with file-by-file accept/reject decisions.
- Add streamed model/tool output to the conversation view.
- Add session rename, delete, export, and import commands to the TUI.
- Add `/agent` selection that changes the active specialist or model policy.
- Add machine-readable event streaming for CLI automation.

## Post-release 0.3.0

### Context and performance

- Ship a documented local embedding model lifecycle: download, cache, upgrade,
  offline use, and removal.
- Add project ignore rules for generated, binary, secret, and dependency paths.
- Add cache invalidation based on model identity, workspace state, and file
  hashes.
- Add context-budget diagnostics and per-run token/latency reporting.
- Benchmark indexing, context selection, cache lookup, and tool execution.

### Observability

- Add opt-in LangSmith tracing for agent graphs and tool calls.
- Add OpenTelemetry-compatible local spans and metrics.
- Redact secrets, credentials, prompts, and sensitive file content by default.
- Add structured run export for support and debugging.

## Security roadmap

- Keep approval-gated mutations as the default.
- Maintain workspace-bound path validation and symlink-escape tests.
- Expand command policy tests for PowerShell, Bash, CMD, and common wrappers.
- Add isolated execution options for untrusted repositories.
- Run dependency, SAST, secret, and license scans in CI.
- Review all third-party provider and embedding dependencies before release.
- Document the threat model and responsible disclosure process.

## Definition of production ready

The project is ready for a public release when:

1. The full CI matrix passes on Windows, Linux, and macOS.
2. A clean environment can install and run the package successfully.
3. At least one credentialed provider passes the live coding-agent acceptance
   flow.
4. Approval, cancellation, rollback, and session-resume flows pass on the
   supported platforms.
5. Dependency and security scans have no unresolved release-blocking findings.
6. The final wheel, source distribution, documentation, and changelog are
   consistent with the tagged version.


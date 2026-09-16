# `devx` Production Roadmap

## Current status

`devx` is at a production-candidate stage for local validation. The core
package, CLI, TUI, LangGraph supervisor, approval controls, sessions, local
context optimization, testing hooks, provider/model configuration commands,
packaging, and CI definitions are in place.

Current local validation:

- 29 automated tests are defined; the suite includes session import/export,
  versioning, and framework-detection coverage.
- Ruff and Python compilation passing.
- Textual pilot tests passing.
- LangChain provider-contract and tool-calling smoke tests passing.
- LangGraph SQLite checkpoint construction passing.
- Wheel build and isolated installation passing.
- Declared dependency audit passing.
- Bandit static security scanning is now part of CI.

## Release 0.1.0 gate

### External validation

- Push the repository to GitHub.
- Run the CI matrix on Windows, Linux, and macOS with Python 3.11–3.13.
- Verify the package job builds, installs, and runs `devx doctor`.
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
- Verify `devx doctor`, `devx sessions`, `devx ask`, and `devx tui` after install.

## Post-release 0.2.0

### Reliability and workflow quality

- Add richer LangGraph interrupt/resume tests across process restarts.
- Add complete approval-history persistence and approval replay rules.
- Add process-tree and cancellation tests on every supported OS.
- Expand test-framework detection with virtual-environment and project-policy
  awareness.
- Add configurable test selection and per-project test policies.
- Add conflict-resolution UX when files change during an agent run.

### User experience

- Add richer diff previews with file-by-file accept/reject decisions.
- Expand streamed model/tool output coverage and rendering quality in the
  conversation view.
- Add comprehensive tests and safer UX around the TUI session rename, delete,
  export, and import commands.
- Make `/agent` selection route to distinct specialist prompts or model
  policies rather than only selecting a requested perspective.
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

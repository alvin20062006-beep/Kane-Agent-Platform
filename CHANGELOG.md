# Changelog

## v2.0.0 - Public Release Readiness

Kane Agent Platform v2.0.0 establishes the Agent OS foundation for local-first agent execution.

### Added

- Task -> Run -> RunStep execution timeline.
- Persistent run and run-step read APIs.
- Kane Memory Ledger with append-only AI writes, Active Snapshot, and Memory Index.
- Exact Retrieval and Native Evidence Search.
- Runtime context budget enforcement.
- Reference candidate and aggregation records.
- Verifier result records linked to runs and run steps.
- Retry / repair attempt records.
- Background Memory Compiler runs and candidates, dry-run by default.
- Manual compiler candidate commit through the existing memory ledger append path.
- Execution Audit UI panels for run steps, reference aggregation, verifier, repair, compiler, memory, and retrieval debug.
- Repeatable local stack scripts: `dev:stack`, `wait:stack`, `stop:stack`, and `test:e2e:smoke`.
- Safer stop / restore guidance for local runtime data.

### Changed

- API, Web, and Local Bridge release version aligned to `2.0.0`.
- Diagnostics, metrics, and Bridge probes optimized with safer cached probe reuse.
- Codex CLI default capabilities aligned with code-agent behavior.
- Task / run / run-step terminal status reconciliation tightened for builtin, failure, and handoff paths.
- Public README and verification docs updated for v2.0.0.

### Safety Boundaries

- Full Memory Ledger is audit data and is not used as prompt memory by default.
- Verifier records store check keys and evidence, not arbitrary shell commands.
- Repair records do not automatically execute high-risk actions.
- Cursor remains handoff-oriented unless real completion callbacks are received.
- Codex permission errors are reported honestly and are not treated as successful execution.

### Deferred Beyond v2.0.0

- Connected Accounts production implementation.
- Credential Vault implementation.
- Multi-Bridge production architecture.
- New MCP capabilities.
- Vector database, embedding, or graph retrieval.
- Full hosted multi-tenant hardening.

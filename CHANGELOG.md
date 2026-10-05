# Changelog

## v3.0.1-beta - 2026-10-05

Security and correctness patch for the v3 beta; no Harness architecture change.

- Web proxy no longer supplies the server API token to anonymous callers; the
  browser supplies an explicit access token for API and SSE when configured.
- Mutating proxy routes consistently reject mismatched request origins.
- External Connector approvals now appear in Turn details using their native
  permission fields, and approval responses must belong to the URL's Turn.
- Next.js and matching tooling updated to 16.3.8; production npm audit now
  reports zero advisories. Removed unused vulnerable `concurrently` dependency.
- API/Web release metadata now reports v3.0.1-beta. SSE tests synchronize with
  subscriptions rather than relying on fixed sleeps.

## v3.0.0-beta - 2026-10-03

New Kane-Kanaloa vNext evaluation baseline. Known and unknown bugs may exist;
this is not a production-readiness claim. v3 succeeds the previously released
v2 with the new thin Harness architecture; historical v2 tags are preserved.
The earlier v0.1.0-beta tag was a naming error and is superseded by v3.0.0-beta.

- Thin model-free Conversation/Message/Turn/Branch Harness and SQLite Store.
- Explicit completion, SSE, partial output and runtime-truth recovery.
- Bundled Kanaloa/modified DSH Harness, Normal/Loop modes and user model configuration.
- Unified external Connector path, Codex reference, Skill/MCP and shared conformance.
- Current human control UI for conversations, Agent connections and runtime facts.
- Release README/notes and upstream third-party license attribution updated.
- Quick typecheck and smoke passed; full suites were not rerun for this release.
- Existing data, configuration, historical commits and tags retained.

## Historical v2 Reference

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

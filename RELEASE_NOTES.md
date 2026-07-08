# Kane Agent Platform v2.0.0 Release Notes

Kane Agent Platform v2.0.0 is the first public release readiness milestone for the local-first Agent OS foundation.

## Release Classification

This release is:

- `Kane Agent Platform v2.0.0`
- local-first
- public repository ready
- suitable for local/private evaluation and development

This release is not:

- a hosted public SaaS
- a credential vault
- a connected accounts platform
- a multi-bridge production mesh
- a RAG/vector retrieval framework
- a workflow engine

## What Works In v2.0.0

- Web, API, and Local Bridge can run together with `npm run dev:stack`.
- `npm run wait:stack` verifies that the local stack is reachable.
- `npm run test:e2e:smoke` performs repeatable browser smoke coverage against the real local stack.
- Tasks create execution attempts as runs.
- Runs contain run steps for the execution timeline.
- Execution Audit exposes run timeline, reference aggregation, verifier, repair, compiler, memory, and retrieval panels.
- Builtin tasks converge task, run, and run-step terminal state.
- Codex CLI adapter status and permission failures are reported honestly.
- Cursor is supported as a handoff-oriented adapter.
- Memory events are append-only for AI writes by default.
- Background Memory Compiler creates candidates first and commits only by explicit action through the ledger append path.
- stop / restore guidance prevents restoring runtime data while API or Bridge is live.

## Verification

Recommended release verification:

```bash
npm install
npm run setup
npm run typecheck:web
npm run test:api
npm run test:bridge
npm run dev:stack
npm run wait:stack
npm run test:e2e:smoke
npm run stop:stack
```

Human acceptance should click through:

```text
Dashboard
Conversation
Settings
Builtin Task
Task Detail
Execution Audit
Run Timeline
Codex Agent
Cursor Agent
Memory
Bridge
Agent Fleet
Dashboard
Stop Stack
Restore
Verify Ports Down
```

## Known Boundaries

- Local model replies require an active model profile or process-level provider key.
- Cursor is not reported as full headless execution unless a real result/callback is received.
- Codex CLI execution depends on local CLI availability and OS permissions.
- The existing `OCTOPUS_*` environment variable and compatibility header names remain in v2.0.0 to avoid breaking local deployments.
- Some internal compatibility IDs still contain legacy names; public UI and docs use Kane v2.0.0 positioning.

## Deferred To Later Releases

- Connected Accounts.
- Credential Vault.
- Multi-Bridge production architecture.
- New MCP capabilities.
- Vector / embedding / graph retrieval.
- Hosted multi-tenant deployment hardening.

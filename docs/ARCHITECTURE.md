# Architecture

This document summarizes the v2.0.0 implementation. The source code and FastAPI OpenAPI schema remain the final authority.

## Repository Layout

```text
kane-agent-platform/
  apps/
    api/           FastAPI control plane
    web/           Next.js UI
    local-bridge/  Local execution and handoff bridge
  packages/
    core/          Shared Python helpers
    schemas/       Shared schemas
  scripts/         Local setup, stack, wait, stop, and E2E scripts
  docs/            Public documentation
```

## Runtime Services

![Kane v2.0.0 architecture](images/kane-v2-architecture.svg)

```text
Web    -> API
API    -> FileStore / optional Postgres
API    -> worker queue
worker -> builtin executor or Local Bridge
Bridge -> local CLI / handoff / webhook / callback
```

Default ports:

```text
Web:    3000
API:    8000
Bridge: 8010
8011:   optional secondary/test bridge port checked during stop/verify
```

Port `8011` is not required by the default stack. It is checked so a secondary local bridge or acceptance-test bridge cannot be left running silently.

## Execution Model

```text
Task
  -> Run (execution attempt)
      -> RunStep (execution timeline)
```

- Task is the user or system goal.
- Run is one execution attempt.
- RunStep records atomic timeline steps such as plan, execute, summarize, verifier, repair, or handoff.
- Evidence, verifier results, repair attempts, reference aggregation, and memory events are separate records linked by reference IDs.

Task, run, and run-step terminal state must not contradict each other. Failure paths must remain honest.

## Platform Execution Loop

Loop in v2.0.0 belongs to the Kane platform. It is not a Kanaloa-private loop and not only the worker queue.

```text
Task
  -> Run
      -> RunStep
          -> worker
              -> builtin executor or Local Bridge
                  -> result / callback / handoff / failure
                      -> task status reconciliation
```

RunStep is the execution timeline. It links to evidence, verifier, repair, reference aggregation, and memory records through reference IDs instead of embedding all business data.

## Builtin Agent And Kanaloa

Kanaloa is the current default built-in AI agent path in v2.0.0. It is seeded as `octopus_builtin`, displayed as `Kanaloa`, and uses adapter type `builtin_octopus`.

Kanaloa is not the Kane platform and is not the memory subsystem. Kane owns the platform services; Kanaloa is one built-in agent runtime path using those services.

The current code does not provide a generic multi-builtin-agent runtime registry. The v2.0.0 public release only documents the built-in Kanaloa path that exists in the code.

## MoA Reference And Aggregator

MoA-style behavior in v2.0.0 is implemented as platform records:

- Reference Candidate
- Aggregator Decision
- RunStep reference links

This layer is platform-owned and optional. It is not Kanaloa-private, and it does not claim automatic multi-model orchestration in v2.0.0.

## Memory Model

```text
Memory Ledger
  -> MemoryEvent
  -> ActiveMemorySnapshot
  -> MemoryIndexEntry
```

- AI automatic writes are append-only by default.
- User-owned delete, rewrite, purge, migrate, and export controls are preserved by the API where implemented.
- Background Memory Compiler creates candidates first.
- Candidate commit uses the existing ledger append path.
- The compiler does not rewrite historical events.

The full ledger is audit data. Runtime prompt context should use Active Snapshot, Relevant Evidence, and Current Run Context instead of the full ledger.

## Retrieval

v2.0.0 has two default retrieval layers:

- Exact Retrieval
- Native Evidence Search

It does not ship vector database, embedding, or graph retrieval as default behavior.

## Verification And Repair

- Verifier results record status, findings, check keys, summaries, and evidence references.
- Verifier does not accept arbitrary shell strings as execution instructions.
- Repair attempts record retry, repair, and trace-rollback intent.
- High-risk repair execution is not automatic.

## Local Bridge

Local Bridge is optional for builtin execution, but required for local external adapter flows such as Codex CLI, Cursor handoff, Claude CLI, local scripts, and generic HTTP/CLI agents.

The Bridge must not pretend unavailable tools are online. Permission errors and missing CLIs are reported honestly.

## Persistence

Default:

```text
apps/data/
apps/local-bridge/data/
```

Both are ignored by Git except `apps/data/.gitkeep`.

Optional PostgreSQL uses the existing store abstraction and compatibility table names. Existing `OCTOPUS_*` environment variable names remain compatible in v2.0.0.

## Public Release Boundaries

v2.0.0 is a local-first Agent OS foundation. It is not a hosted multi-tenant SaaS, credential vault, connected accounts implementation, or multi-bridge production architecture.

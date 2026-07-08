# Kane API Overview

Kane Agent Platform v2.0.0 exposes a FastAPI control-plane API. The authoritative schema is available at:

```text
http://127.0.0.1:8000/docs
```

Default persistence is local file-backed JSON under `apps/data/`. Optional PostgreSQL support uses the existing store abstraction.

## Base URLs

```text
API:    http://127.0.0.1:8000
Bridge: http://127.0.0.1:8010
Web:    http://127.0.0.1:3000
```

## Health And Diagnostics

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Lightweight API liveness, version, persistence, startup summary |
| GET | `/health/diagnostics` | Heavier diagnostics for tasks, runs, Bridge, watchdog, and profiling |
| GET | `/metrics` | Aggregated runtime metrics |
| GET | `/watchdog` | Watchdog summary |
| GET | Bridge `/health` | Lightweight Local Bridge liveness |
| GET | Bridge `/v1/status` | Bridge adapter status |

Diagnostics and metrics may reuse short-lived cached Bridge probes to reduce duplicate load. They must still report failures honestly.

## Tasks, Runs, And Execution Audit

| Method | Path | Purpose |
|---|---|---|
| GET | `/tasks` | List tasks |
| POST | `/tasks` | Create a task |
| GET | `/tasks/{task_id}` | Read a task |
| POST | `/tasks/{task_id}/assign` | Assign a task to an agent |
| POST | `/tasks/{task_id}/run` | Create a run and enqueue execution |
| POST | `/tasks/{task_id}/retry` | Create a retry attempt |
| POST | `/tasks/{task_id}/approve` | Approve a waiting task |
| POST | `/tasks/{task_id}/reject` | Reject a waiting task |
| GET | `/tasks/{task_id}/timeline` | Task events, run logs, and audit context |
| GET | `/runs` | List runs |
| GET | `/runs/{run_id}` | Read a run |
| GET | `/runs/{run_id}/steps` | Read run steps |

Execution hierarchy:

```text
Task
  -> Run (execution attempt)
      -> RunStep (execution timeline)
```

RunStep is not a memory record. It stores execution timeline state and reference IDs to related records such as verifier results, repair attempts, reference aggregations, and evidence.

## Memory

| Method | Path | Purpose |
|---|---|---|
| GET | `/memory` | Legacy-compatible memory item view |
| POST | `/memory` | Legacy-compatible memory write path |
| DELETE | `/memory/{memory_id}` | User-owned delete path |
| GET | `/memory/events` | Memory ledger events |
| POST | `/memory/events` | Append memory event |
| GET | `/memory/index` | Current memory index |
| GET | `/memory/snapshot` | Active memory snapshot |
| GET | `/memory/compiler/runs` | Compiler runs |
| POST | `/memory/compiler/runs` | Create a compiler run, dry-run by default |
| GET | `/memory/compiler/candidates` | Compiler candidates |
| POST | `/memory/compiler/candidates/{candidate_id}/commit` | Manually commit a candidate through the ledger append path |

AI writes are append-only by default. User-controlled delete, rewrite, purge, migrate, and export semantics are preserved where implemented by the existing API. The full ledger is an audit record and is not inserted into prompts by default.

## Retrieval

| Method | Path | Purpose |
|---|---|---|
| POST | `/retrieval/exact` | Exact lookup by supported IDs/keys |
| POST | `/retrieval/evidence-search` | Native Evidence Search across Kane-owned data |
| POST | `/runtime-context` | Runtime context with budgeted snapshot, evidence, and current run context |

v2.0.0 uses two retrieval layers only:

- Exact Retrieval
- Native Evidence Search

It does not ship vector database, embedding, or graph retrieval as default retrieval layers.

## Reference, Verifier, And Repair

| Method | Path | Purpose |
|---|---|---|
| POST | `/runs/{run_id}/reference-candidates` | Record reference candidate advice |
| GET | `/runs/{run_id}/reference-candidates` | List run reference candidates |
| POST | `/runs/{run_id}/reference-aggregations` | Record an aggregation decision |
| GET | `/runs/{run_id}/reference-aggregations` | List run aggregation decisions |
| POST | `/runs/{run_id}/verifier-results` | Record verifier result |
| GET | `/runs/{run_id}/verifier-results` | List verifier results |
| POST | `/runs/{run_id}/repair-attempts` | Record repair attempt |
| GET | `/runs/{run_id}/repair-attempts` | List repair attempts |

Verifier records do not execute arbitrary shell strings. They store `command_key` or `check_key` references and status evidence. Repair does not automatically execute high-risk changes.

## Conversations

| Method | Path | Purpose |
|---|---|---|
| GET | `/conversations` | List conversations |
| POST | `/conversations` | Create a conversation |
| GET | `/conversations/{conversation_id}` | Read conversation and messages |
| PATCH | `/conversations/{conversation_id}` | Update metadata |
| DELETE | `/conversations/{conversation_id}` | Delete conversation |
| POST | `/conversations/{conversation_id}/messages` | Add a message |
| POST | `/conversations/{conversation_id}/promote` | Promote conversation content into a task |

If no model profile or process-level key is configured, conversation send should be disabled with a clear no-model state.

## Agents And Local Bridge

| Method | Path | Purpose |
|---|---|---|
| GET | `/agents` | List agents |
| GET | `/agents/{agent_id}` | Read agent, bridge status, and profile binding |
| POST | `/agents` | Create agent metadata |
| PATCH | `/agents/{agent_id}` | Update agent metadata |
| DELETE | `/agents/{agent_id}` | Delete non-protected agent |
| POST | `/agents/{agent_id}/test-run` | Run a low-risk adapter test |
| GET | `/local-bridge` | Read registered bridge agents |
| POST | `/local-bridge/probe` | Probe the Local Bridge |
| POST | `/local-bridge/register` | Register a bridge-side agent |
| POST | `/local-bridge/result` | Submit a bridge result |
| POST | `/integrations/bridge/complete` | Local Bridge callback for task/run completion |

If `OCTOPUS_BRIDGE_SHARED_SECRET` is configured, Bridge requests use the existing `X-Octopus-Bridge-Key` header for compatibility. The name is retained for v2.0.0 compatibility.

## Skills, Files, Reports, Policies

Additional platform resources are available through the FastAPI schema:

- `/skills`
- `/files`
- `/reports`
- `/policies`
- `/notifications`
- `/observer`
- `/advisor`
- `/governor`
- `/escalations`

Use `/docs` as the source of truth for request and response models.

## Version

Responses that include `version` should report `2.0.0` for the v2.0.0 release. Version fields indicate platform release alignment; they do not imply mock data.

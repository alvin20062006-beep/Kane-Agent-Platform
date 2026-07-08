# Kane Agent OS Foundation

Status: PR-9 foundation documentation

Kane is a local-first Agent Operating System for agent execution. It is not a memory framework, not a RAG framework, and not a workflow engine. Memory, retrieval, reference review, verifier records, repair records, compiler candidates, and UI audit panels exist to support traceable agent execution.

## Run Locally

From the repository root:

```powershell
npm.cmd run dev:api
npm.cmd run dev:bridge
npm.cmd run dev:web
```

Or start the stack together:

```powershell
npm.cmd run dev:stack
```

Default local URLs:

- API: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Web: `http://localhost:3000`
- Local Bridge: `http://127.0.0.1:8010`

## Baseline Checks

Every PR in the Agent OS foundation must pass:

```powershell
npm.cmd run typecheck:web
npm.cmd run test:bridge
npm.cmd run test:api
```

The Web typecheck is the current UI regression gate. The API suite contains focused tests for Run / RunStep, Memory Ledger, Retrieval, Reference / Aggregator, Verifier, Repair, and Background Memory Compiler.

## Inspect The UI

Task execution audit:

1. Open `http://localhost:3000/tasks`.
2. Open a task detail page.
3. Use the `Execution Audit` section.
4. Inspect:
   - Run Timeline / RunStep records
   - Reference candidates
   - Aggregator decisions
   - Verifier results
   - Repair attempts
   - Memory Compiler runs and candidates

Memory audit:

1. Open `http://localhost:3000/memory`.
2. Use the `Ledger / Snapshot` tab to inspect:
   - Memory events
   - Memory index
   - Active snapshot
3. Use the `Retrieval Debug` tab to inspect:
   - Exact Retrieval
   - Native Evidence Search
   - Runtime Context

The UI is an inspect, audit, and control surface. It must not become a hidden business logic layer.

## Architecture Baseline

### Task -> Run -> RunStep

The execution hierarchy is:

```text
Task
  -> Run (Execution Attempt)
      -> RunStep
```

- `Task` is the user or system goal.
- `Run` is one execution attempt.
- A task can have multiple runs.
- `RunStep` belongs to one run and represents an atomic execution timeline step.
- Retry, resume, and repair must not silently rewrite the original run history.

### RunStep Is Timeline, Not Memory

`RunStep` records what happened during execution. It can reference evidence, verifier results, repair attempts, decisions, and memory events through IDs.

`RunStep` must not become a container for all business data.

### Memory Ledger vs Active Snapshot

`MemoryEvent` is the historical fact ledger. AI automatic writes are append-only.

`ActiveMemorySnapshot` is the prompt-eligible memory projection. Runtime context should default to:

```text
Active Snapshot
Relevant Evidence
Current Run Context
```

The full Memory Ledger must not be injected directly into prompts.

### AI Append-Only vs User Ownership

AI writes are append-only by default:

- append event
- supersede event
- invalidate event
- compiler candidate commit through `append_memory_event()`

User ownership remains final. User-controlled delete, rewrite, purge, migrate, and export operations are allowed by design and must keep clear semantics.

### Retrieval

Kane default retrieval has exactly two layers:

```text
Kane Memory Retrieval
  -> Exact Retrieval
  -> Native Evidence Search
```

Do not add a third default retrieval framework. If a Kane-owned source is missing, extend Native Evidence Search.

### Background Memory Compiler

The compiler flow is:

```text
Execution Evidence
  -> MemoryCompilerRun
  -> MemoryCompilerCandidate
  -> manual candidate commit
  -> append_memory_event()
  -> Memory Index / Active Snapshot projection
```

Compiler runs are dry-run by default. A candidate must be persisted before it can be committed. Commit is manual and must call the existing ledger append path.

The compiler must not directly mutate `MemoryIndexEntry`, `ActiveMemorySnapshot`, or historical `MemoryEvent` records.

## PR-1 To PR-8 Foundation Content

- PR-1: Loop State Machine with `Run` and `RunStep`, plus base `plan`, `execute`, and `summarize` steps.
- PR-2: Kane Memory Ledger with `MemoryEvent`, `MemoryIndexEntry`, `ActiveMemorySnapshot`, legacy MemoryItem compatibility, and user ownership controls.
- PR-3: Exact Retrieval, Native Evidence Search, and runtime context budget.
- PR-4: Reference candidates and aggregator decisions attached to RunStep.
- PR-5: Verifier interface and `VerifierResult` records.
- PR-6: Retry / Repair Loop with `RepairAttempt`, retry limits, confirmation gates, and no direct dangerous execution.
- PR-7: Background Memory Compiler with dry-run candidate persistence and manual commit into the append-only ledger.
- PR-8: UI audit panels for execution timeline, reference / aggregator, verifier, repair, compiler, ledger, snapshot, and retrieval debug.

## Regression Guardrails

Do not regress these boundaries:

- Do not introduce a third default retrieval layer.
- Do not put the full Memory Ledger directly into prompts.
- Do not make UI components perform hidden business logic.
- Do not let Repair automatically execute high-risk actions.
- Do not let the Compiler automatically pollute long-term memory.
- Do not mutate historical MemoryEvent records for AI behavior.
- Do not collapse RunStep timeline records into Memory Ledger records.
- Do not remove user delete, rewrite, purge, migrate, or export authority.

## Future Work Gate

New features after PR-9 must go through ACP / Blueprint Review before implementation.

The review should state:

- which Agent OS execution problem is being solved
- which existing model, service, API, or UI surface is affected
- whether Memory, Retrieval, Repair, Compiler, or UI semantics change
- the exact regression tests required
- rollback behavior

No future PR should hide architecture changes inside tests, docs, or UI-only code.

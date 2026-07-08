# Kane Agent Operating System Optimization Blueprint

Status update: v2.0.0 Agent OS Foundation complete
Foundation doc: `docs/AGENT_OS_FOUNDATION.md`

Current foundation scope:

- PR-1 Loop State Machine: `Task -> Run -> RunStep`
- PR-2 Memory Ledger: append-only AI events, active snapshot, memory index, user ownership controls
- PR-3 Retrieval: Exact Retrieval + Native Evidence Search + runtime context budget
- PR-4 Reference Layer + Aggregator
- PR-5 Verifier Interface
- PR-6 Retry / Repair Loop
- PR-7 Background Memory Compiler: dry-run candidates, manual commit through `append_memory_event()`
- PR-8 UI audit surfaces
- PR-9 Tests / Documentation

Future feature work must go through ACP / Blueprint Review before implementation.

---

Status: historical implementation blueprint for the v2.0.0 Agent OS Foundation
Baseline commit: `origin/main @ f6d272c` legacy baseline
Scope: design history and release context, not a separate runtime module

Terminology note for v2.0.0 public release: Kanaloa is the current default built-in AI agent path. Loop, Memory Ledger, Retrieval, Reference Aggregation, Verifier, Repair, and Compiler are Kane platform capabilities, not Kanaloa-private subsystems.

---

## 1. Core Positioning

Kane is a local-first Agent Operating System for agent execution.

Kane is not a memory framework, not a retrieval framework, and not a workflow engine. Memory, loop, reference aggregation, verification, retry, and repair exist to make agent execution traceable, inspectable, recoverable, and controllable.

The optimization direction is therefore:

```text
Agent Execution
  -> Loop State
  -> Run / RunStep Trace
  -> Native Memory
  -> Native Retrieval
  -> Reference Aggregation
  -> Verification
  -> Repair
  -> UI / Audit
```

All final code, module names, database structures, API names, UI names, and docs should converge to Kane Native Architecture naming. Public research directions may inspire design, but final implementation should not embed external project names.

---

## 2. PR-0 Legacy Baseline

Current selected baseline:

```text
origin/main @ f6d272c
tag: legacy baseline
work base: v2.0 foundation branch
```

Why this baseline:

- It contains the selected legacy public snapshot used as the clean starting point.
- It includes existing Kanaloa orchestrator, action gateway, permission profile, adapter status, verification planning, and UI surfaces.
- Local `main` and `origin/main` had no common ancestor after the remote forced update, so the correct strategy is to base work on `origin/main` and migrate selected patches.

PR-0 migrated patches:

- `FileStore` JSON read cache and file-backed persistence stability.
- Local Bridge state lock, unique temp file writes, and short retry around atomic replace.
- Local Bridge smoke tests.
- Node-based Python runner and setup wrappers.
- Minimal API smoke tests.
- Non-conflicting product copy for README, skills UI, and i18n.

Current baseline checks:

```text
npm.cmd run typecheck:web  -> pass
npm.cmd run test:bridge    -> pass, 2 passed
npm.cmd run test:api       -> pass, 3 passed
```

---

## 3. Current Implementation Audit

### 3.1 Existing Strengths

The legacy baseline codebase already had a usable agent control plane foundation:

- Next.js web UI under `apps/web`.
- FastAPI API under `apps/api`.
- Local Bridge under `apps/local-bridge`.
- File-backed persistence with optional Postgres configuration.
- Agents, tasks, skills, conversations, files, memory candidates, reports, policies, watchdog, governor, and adapter status surfaces.
- Kanaloa internal agent identity and permission profiles.
- Kanaloa action gateway for task creation, dispatch, observation, cancellation, and recent task listing.
- Kanaloa orchestrator master task and subtask runtime.
- Verification subtask planning and honest verification result mapping.
- Runtime audit fields such as `TaskEventRecord`, `RunLogLine`, input snapshots, output snapshots, and watchdog issues.

### 3.2 Existing Model Surface

Important current models:

- `Task`
- `TaskAssignment`
- `Skill`
- `MemoryItem`
- `Conversation`
- `ConversationMessage`
- `GovernorDecision`
- `TaskEventRecord`
- `RunLogLine`
- `OrchestratorMasterTask`
- `OrchestratorSubtaskRecord`

Important current services:

- `task_lifecycle.py`
- `worker_queue.py`
- `runtime_audit.py`
- `runtime_supervision.py`
- `kanaloa_actions.py`
- `kanaloa_platform.py`
- `kanaloa_orchestrator.py`
- `kanaloa_observer.py`
- `verification_runner.py`
- `permission_gate.py`

### 3.3 Gaps Against Target Blueprint

These are conflicts or missing surfaces that must be resolved by the roadmap. They should not be silently overwritten.

1. Loop state is task-centric, not yet Run / RunStep-centric.
   - Existing `Task` has `status`, `retry_count`, `last_run_id`, `needs_attention`, and recovery fields.
   - Existing `RunLogLine` records logs and snapshots.
   - Missing: first-class `Run` + `RunStep` state machine with explicit transitions and append-only step history.

2. Orchestrator subtasks exist, but they are not the universal execution trace.
   - `OrchestratorMasterTask` and `OrchestratorSubtaskRecord` are specific to Kanaloa orchestration.
   - PR-1 should not simply rename orchestrator subtasks into RunSteps.
   - Correct direction: create a general Loop State Machine layer and map orchestrator subtasks onto it.

3. Memory is currently mutable item storage, not native ledger memory.
   - Existing `MemoryItem` supports candidate / approved / rejected and source fields.
   - Missing: append-only `MemoryEvent`, active snapshots, supersede/invalidate chains, configurable memory policy, and memory index.

4. Runtime prompt memory is not yet formally budgeted.
   - Existing conversation flow can include platform snapshots and memory search behavior.
   - Missing: explicit prompt memory contract limiting runtime context to Active Snapshot, Relevant Evidence, and Current Run Context.

5. Retrieval is not yet Kane Memory Retrieval.
   - Existing retrieval is mostly list/filter/search over stored data.
   - Missing: Exact Retrieval and Native Evidence Search as the only default retrieval layers.

6. Verification exists as orchestration planning, not a standalone interface.
   - `verification_runner.py` creates verification subtask specs.
   - Missing: stable verifier interface that writes results onto RunStep / Memory evidence rather than only orchestrator records.

7. Repair/retry exists in runtime supervision and task lifecycle, but is not yet a typed loop.
   - Existing retry uses task status and watchdog decisions.
   - Missing: repair loop that consumes failure evidence, verifier output, and RunStep state.

8. Policies are scattered across environment and service logic.
   - Existing permission profiles and adapter gates are useful.
   - Missing: configurable memory policies such as `memory_admission_policy`, `retrieval_policy`, `retention_policy`, `deletion_policy`, and `external_memory_policy`.

---

## 4. Native Architecture Principles

### 4.1 Naming

Use Kane-native naming in final implementation:

- `KanePlatformLoop`
- `Run`
- `RunStep`
- `KaneMemoryLedger`
- `MemoryEvent`
- `ActiveMemorySnapshot`
- `KaneMemoryRetrieval`
- `ExactRetrieval`
- `NativeEvidenceSearch`
- `ReferenceLayer`
- `Aggregator`
- `Verifier`
- `RepairLoop`
- `BackgroundMemoryCompiler`

Do not introduce external project names into module names, class names, database tables, API routes, UI labels, or docs.

### 4.2 Agent Execution First

Every new layer must answer one execution question:

- What is the agent doing?
- Why is it doing it?
- What evidence did it use?
- What did it change?
- How was the result verified?
- If it failed, what repair action is allowed?
- What memory should survive the run?

If a proposed feature does not improve agent execution, traceability, or recovery, it should not enter the PR.

### 4.3 Append-Only Is Storage, Not Prompt

Append-only ledger is an audit and storage strategy. It is not a prompt strategy.

Runtime context should default to:

```text
Active Snapshot
Relevant Evidence
Current Run Context
```

The full memory ledger must not be placed directly into prompts.

### 4.4 User Owns Memory

Append-only constraints apply to AI automatic writes by default.

If the user explicitly asks to delete, rewrite, purge, migrate, or export memory, Kane must allow the operation through user-controlled APIs and audit the operation honestly.

AI behavior should remain auditable. User control remains final.

### 4.5 Timeline And Ledger Separation

RunStep is the execution timeline. It records what happened during execution.

Memory Ledger is the historical fact ledger. It records which facts, decisions, failures, preferences, skill outcomes, verification results, or lessons should be retained beyond the current execution.

These responsibilities must stay separate:

- Do not treat RunStep as memory.
- Do not treat Memory Ledger as an execution log.
- RunStep links to evidence, decisions, verifier results, repair records, and memory events by reference ID.
- Memory Ledger stores durable knowledge and audit-worthy facts, not every transient execution detail.

---

## 5. Target Runtime Shape

### 5.1 Execution Loop

Target loop:

```text
Run Created
  -> Step Planned
  -> Step Started
  -> Evidence Attached
  -> Tool / Agent Action Requested
  -> Action Completed
  -> Result Captured
  -> Verification Requested
  -> Verification Completed
  -> Memory Admission Evaluated
  -> Step Completed / Failed / Blocked
  -> Repair or Next Step
  -> Run Completed / Failed / Cancelled
```

The loop should be implemented as a state machine with explicit transition rules.

### 5.2 Task / Run / RunStep Hierarchy

The execution hierarchy is:

```text
Task
  -> Run (Execution Attempt)
      -> RunStep
```

- `Task` is the user or system goal.
- `Run` is one execution attempt for that goal.
- A single `Task` can have multiple `Run` records.
- `RunStep` belongs to exactly one `Run`.
- Retry, resume, and repair should create new attempts or new linked steps instead of polluting the original Run history.

### 5.3 Run

`Run` is one execution attempt. It should represent a concrete attempt to satisfy a task, conversation request, orchestrator request, or skill execution.

Candidate fields:

- `run_id`
- `task_id`
- `conversation_id`
- `parent_run_id`
- `status`
- `objective`
- `initiator`
- `assigned_agent_id`
- `permission_profile`
- `created_at`
- `updated_at`
- `started_at`
- `completed_at`
- `cancelled_at`
- `failure_id`
- `summary`
- `current_step_id`
- `metadata`

### 5.4 RunStep

`RunStep` is the atomic step on the execution timeline.

RunStep should not carry all business data. Evidence, verifier results, decisions, repair records, and memory events should exist as independent records. RunStep should connect to them through reference IDs.

Candidate fields:

- `run_step_id`
- `run_id`
- `parent_step_id`
- `step_type`
- `status`
- `title`
- `instruction`
- `agent_id`
- `skill_id`
- `tool_call_id`
- `decision_id`
- `failure_id`
- `input_context_ref`
- `evidence_refs`
- `output_ref`
- `verification_ref`
- `repair_ref`
- `memory_event_refs`
- `attempt_index`
- `created_at`
- `started_at`
- `completed_at`
- `metadata`

RunStep should be append-friendly and auditable. A step can be superseded or repaired through linked records or follow-up steps, but historical step records should not be silently rewritten.

---

## 6. Kane Native Memory

### 6.1 Storage Layers

Target memory layers:

```text
Kane Native Memory
  -> Memory Ledger
  -> Active Snapshot
  -> Memory Index
  -> Evidence Links
  -> User Ownership Controls
```

### 6.2 Memory Ledger

The ledger is append-only for automatic AI writes.

Candidate event types:

- `observed`
- `claimed`
- `decision_recorded`
- `preference_recorded`
- `skill_result_recorded`
- `failure_recorded`
- `verification_recorded`
- `snapshot_created`
- `superseded`
- `invalidated`
- `user_deleted`
- `user_rewritten`
- `user_purged`
- `exported`
- `migrated`

Candidate fields:

- `event_id`
- `memory_id`
- `event_type`
- `subject_key`
- `scope_type`
- `scope_id`
- `source_type`
- `source_id`
- `run_id`
- `run_step_id`
- `task_id`
- `conversation_id`
- `skill_id`
- `decision_id`
- `failure_id`
- `content_json`
- `value_json`
- `evidence_refs`
- `confidence`
- `policy_result`
- `supersedes_event_id`
- `invalidates_event_id`
- `created_by`
- `created_at`
- `metadata`

MemoryEvent content should be structured, not a single text blob. `content_json` or `value_json` should support different event shapes for facts, decisions, failures, skill results, preferences, verification records, and other durable memory types.

### 6.3 Active Snapshot

Active Snapshot is the runtime memory surface.

It should contain only compact, current, policy-admitted memory:

- stable user preferences
- active project facts
- current task facts
- agent execution facts
- recent unresolved failures
- verified decisions
- relevant skill outcomes

It should not contain the full ledger.

### 6.4 Background Memory Compiler

The Background Memory Compiler may:

- append new events
- create supersede events
- create invalidate events
- update active snapshot
- update memory index

The compiler must not:

- rewrite historical events
- merge historical events in place
- delete history
- silently mutate audit records

### 6.5 Configurable Memory Policy

Memory policy must not be hard-coded.

Target configurable policies:

- `memory_admission_policy`
- `retrieval_policy`
- `retention_policy`
- `deletion_policy`
- `external_memory_policy`

Default policies can exist, but user configuration must decide final behavior.

---

## 7. Kane Memory Retrieval

Default retrieval has exactly two layers:

```text
Kane Memory Retrieval
  -> Exact Retrieval
  -> Native Evidence Search
```

No third default retrieval framework should be introduced.

### 7.1 Exact Retrieval

Exact Retrieval handles direct lookup keys:

- `subject_key`
- `task_id`
- `run_id`
- `event_id`
- `memory_id`
- `skill_id`
- `decision_id`
- `failure_id`
- `conversation_id`

### 7.2 Native Evidence Search

Native Evidence Search handles evidence from Kane-owned data sources:

- workspace
- raw logs
- conversation logs
- task logs
- evidence
- summaries
- memory events
- run logs
- skills
- decisions
- failures

If current implementation cannot cover a source, extend Native Evidence Search. Do not add a third retrieval layer.

### 7.3 Runtime Memory Budget

Runtime context default:

```text
Active Snapshot
Relevant Evidence
Current Run Context
```

Prompt construction should enforce budget and provenance:

- Include only selected evidence.
- Include source references.
- Prefer summarized active snapshot over raw ledger.
- Never dump the full ledger into prompt context.

---

## 8. Reference Layer And Aggregator

The Reference Layer collects candidate perspectives and evidence for a RunStep.

Native naming:

- `ReferenceLayer`
- `ReferenceCandidate`
- `ReferenceEvidence`
- `Aggregator`

Responsibilities:

- collect candidate answers or plans from available agents, skills, or internal reasoning paths
- attach evidence references
- score confidence and risk
- preserve dissenting evidence when useful
- select or synthesize final step output
- write aggregation result to RunStep output and evidence links

The Aggregator must not hide uncertainty. It should record:

- candidates considered
- selected candidate
- rejected candidates
- evidence used
- confidence
- known gaps
- verifier requirements

---

## 9. Verifier Interface

The legacy baseline had verification planning through `verification_runner.py` and orchestrator verification summaries. This should become a stable verifier interface after Run / RunStep exists.

Target interface:

- `verification_id`
- `run_id`
- `run_step_id`
- `verifier_type`
- `command_key`
- `input_refs`
- `status`
- `started_at`
- `completed_at`
- `exit_code`
- `output_summary`
- `error_summary`
- `evidence_refs`
- `memory_event_refs`

Verifier results should be attachable to:

- RunStep
- MemoryEvent
- Failure record
- Repair decision

Verifier must never mark a result passed unless an actual check succeeded.

---

## 10. Retry And Repair Loop

Repair should run on top of RunStep, Memory, Evidence, and Verifier.

Target repair flow:

```text
Failure Detected
  -> Failure Evidence Captured
  -> Repair Policy Checked
  -> Repair Plan Created
  -> Repair Step Executed
  -> Verification Step Executed
  -> Original Step Superseded or Run Failed
```

Repair must respect:

- max attempts
- permission profile
- user approval rules
- tool risk
- memory policy
- verifier requirements

Repair should not mutate historical RunStep or MemoryEvent records in place.

---

## 11. UI Direction

UI should expose execution state first, not memory internals first.

Target UI surfaces:

- Run timeline
- RunStep details
- evidence panel
- active snapshot panel
- verifier panel
- repair panel
- memory ledger audit view
- memory ownership controls
- policy configuration

The UI should make clear:

- what is running
- what has failed
- what evidence was used
- what was verified
- what repair is proposed
- what memory was written
- what user controls are available

---

## 12. Roadmap

Correct implementation sequence:

```text
PR-1  Loop State Machine (Run / RunStep)
PR-2  Kane Memory Ledger
PR-3  Kane Memory Retrieval
PR-4  MoA Reference Layer + Aggregator
PR-5  Verifier Interface
PR-6  Retry / Repair Loop
PR-7  Background Memory Compiler
PR-8  UI
PR-9  Tests / Documentation
```

### PR-1 Loop State Machine

Goal:

- Add first-class `Run` and `RunStep`.
- Preserve existing Task and orchestrator behavior.
- Map current task execution and orchestrator subtasks onto the new loop trace gradually.

Non-goals:

- no memory ledger
- no retrieval redesign
- no aggregator
- no repair loop rewrite

Expected work:

- define models
- define state transitions
- add repository support
- write append-style RunStep events
- expose minimal read APIs
- add focused tests

### PR-2 Kane Memory Ledger

Goal:

- Add append-only memory event storage for AI automatic writes.
- Keep existing `MemoryItem` compatibility where needed.
- Add active snapshot primitive.

Non-goals:

- no broad retrieval framework
- no UI redesign
- no compiler automation yet

### PR-3 Kane Memory Retrieval

Goal:

- Implement Exact Retrieval.
- Implement Native Evidence Search over Kane data sources.
- Enforce runtime memory budget.

Non-goals:

- no third retrieval system
- no direct full ledger prompt injection

### PR-4 Reference Layer + Aggregator

Goal:

- Add native reference candidate collection.
- Add aggregator result model.
- Attach aggregation evidence to RunStep.

Non-goals:

- no unrelated model-provider abstraction expansion
- no UI-heavy work

### PR-5 Verifier Interface

Goal:

- Turn existing verification planning into stable verifier records.
- Attach verifier results to RunStep and evidence.

Non-goals:

- no fake pass results
- no broad repair loop

### PR-6 Retry / Repair Loop

Goal:

- Add typed repair flow over failure evidence and verifier results.
- Respect policy, approval, and attempt limits.

Non-goals:

- no history rewrite
- no automatic risky repair without policy approval

### PR-7 Background Memory Compiler

Goal:

- Compile ledger events into active snapshot and index.
- Only append/supersede/invalidate events.

Non-goals:

- no historical event mutation
- no user ownership restriction

### PR-8 UI

Goal:

- Expose Run, RunStep, evidence, verifier, repair, memory snapshot, and memory audit views.

Non-goals:

- no decorative redesign
- no new behavior hidden behind UI-only state

### PR-9 Tests / Documentation

Goal:

- Harden regression tests and public docs.
- Document policy, memory ownership, retrieval budget, and operator controls.

Non-goals:

- no architecture changes hidden in docs PR

---

## 13. Testing Gates

Minimum baseline for every PR:

```text
npm.cmd run typecheck:web
npm.cmd run test:bridge
npm.cmd run test:api
```

Additional gates should be added only when a PR touches the relevant surface.

Examples:

- PR-1: Run / RunStep state transition tests.
- PR-2: MemoryEvent append-only tests.
- PR-3: retrieval policy and prompt budget tests.
- PR-4: aggregation provenance tests.
- PR-5: verifier status accuracy tests.
- PR-6: repair attempt limit and approval tests.
- PR-7: compiler no-history-mutation tests.
- PR-8: UI typecheck and focused component tests if available.

---

## 14. Anti-Garbage-Code Rules For This Roadmap

Every PR must follow these constraints:

1. Solve one target only.
2. Do not do broad refactors.
3. Do not introduce new dependencies without explicit approval.
4. Do not create temporary files in the repo.
5. Do not duplicate helper stacks.
6. Do not commit debug code.
7. Do not create parallel APIs for the same concept.
8. Preserve current API, UI, and Bridge behavior unless the PR explicitly changes it.
9. Report scope expansion before doing it.
10. Keep Kane Native Architecture naming.
11. Do not implement future roadmap modules early.
12. Do not write fake implementations just to pass tests.

---

## 15. Immediate Next Decision

PR-0 is complete enough for review:

- Legacy baseline selected.
- Local valuable patches migrated.
- API smoke test added.
- Baseline checks pass.
- Blueprint generated.

Next action after user approval:

```text
Start PR-1: Loop State Machine (Run / RunStep)
```

PR-1 should begin with a narrow design pass over existing `Task`, `RunLogLine`, `TaskEventRecord`, `OrchestratorMasterTask`, and `OrchestratorSubtaskRecord`, then add the minimum Run / RunStep model and transition tests.

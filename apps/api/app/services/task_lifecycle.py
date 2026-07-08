from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from ..executor import execute_builtin_octopus, execute_via_local_bridge
from ..fsm import TaskEvent, TaskState, can_transition, transition
from ..id_utils import new_id
from ..settings_env import get_default_max_recovery_attempts
from .policy_engine import build_policy_override_until, evaluate_task_run
from .worker_queue import enqueue_run
from ..models import (
    ApprovalKind,
    ApprovalStatus,
    Agent,
    AgentCapabilities,
    AgentStatus,
    BridgeCompleteBody,
    ExecutionPlan,
    ExecutionStep,
    ExecutionStepStatus,
    LocalBridgeAgentState,
    LocalBridgeRegisterBody,
    LocalBridgeResultBody,
    MemoryItem,
    Run,
    RunLogLine,
    TaskAssignment,
    TaskApproval,
    Task,
    TaskAssignBody,
    TaskApproveBody,
    TaskCreateBody,
    TaskEventRecord,
    TaskFailBody,
    TaskRejectBody,
    TaskStatus,
    WatchdogEvent,
)
from ..pagination import (
    DEFAULT_TIMELINE_EVENTS_LIMIT,
    DEFAULT_TIMELINE_LOGS_LIMIT,
)
from ..store.run_log_queries import list_logs_for_runs, list_logs_for_run
from ..store.task_event_queries import list_events_for_task
from .orchestrator_lookup import find_master_context_for_platform_task
from ..store.repositories import (
    agents_repo,
    approvals_repo,
    execution_plans_repo,
    local_bridge_repo,
    memory_repo,
    run_logs_repo,
    runs_repo,
    task_assignments_repo,
    task_events_repo,
    tasks_repo,
    watchdog_events_repo,
)
from .notifications import deliver_watchdog_event
from .advisor import upsert_advisor_suggestion
from .memory_ledger import record_memory_item_event
from .runtime_audit import (
    append_task_event,
    append_watchdog_issue,
    build_environment_summary,
    build_run_input_snapshot,
    claim_processed_receipt,
    ensure_task_correlation,
    finalize_processed_receipt,
    make_receipt_key,
    mark_task_attention,
    now_iso,
    resolve_parent_run_id,
)
from .run_steps import complete_run_timeline, ensure_base_run_steps, mark_run_step
from .task_status_reconciliation import reconcile_task_with_run


def _now_iso() -> str:
    return now_iso()


def _task_state(ts: TaskStatus) -> TaskState:
    return TaskState(ts.value)


def _apply_task_status(task: Task, new_status: TaskStatus) -> Task:
    return task.model_copy(update={"status": new_status, "updated_at": _now_iso()})


def _append_event(task_id: str, typ: str, message: str | None, payload: dict[str, Any] | None = None) -> TaskEventRecord:
    task = tasks_repo.get(task_id)
    return append_task_event(
        task_id,
        typ,
        message,
        correlation_id=task.correlation_id if task else None,
        payload=payload,
    )


def _append_run_log(run_id: str, seq: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
    run = runs_repo.get(run_id)
    line = RunLogLine(
        log_id=new_id("log"),
        run_id=run_id,
        seq=seq,
        level=level,  # type: ignore[arg-type]
        message=message,
        meta=meta,
        created_at=_now_iso(),
        correlation_id=run.correlation_id if run else None,
    )
    run_logs_repo.upsert(line)


def _append_watchdog_event(
    typ: str,
    message: str,
    severity: str = "info",
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    recovery_hint: str | None = None,
) -> None:
    task = tasks_repo.get(task_id) if task_id else None
    ev = append_watchdog_issue(
        typ,
        message,
        severity=severity,
        task=task,
        agent_id=agent_id,
        recovery_hint=recovery_hint,
        source="human" if typ == "operator_mark_failed" else "watchdog",
    )
    # Best-effort: notify enabled channels
    try:
        deliver_watchdog_event(ev.model_dump())
    except Exception:
        pass


def _update_local_bridge_callback_state(body: LocalBridgeResultBody) -> None:
    existing = local_bridge_repo.get(body.agent_id)
    if not existing:
        return
    updated_state = existing.model_copy(
        update={
            "last_seen_at": _now_iso(),
            "last_task_id": body.task_id,
            "last_run_id": body.run_id,
            "last_result_status": body.status,
            "last_error": body.error,
            "status": "idle" if body.status == "succeeded" else "degraded",
        }
    )
    local_bridge_repo.upsert(updated_state)


def _upsert_task_memory(task: Task, run: Run, output: str | None, *, status: str) -> None:
    title = f"Task memory: {task.title}"
    existing = None
    for item in memory_repo.list():
        if item.scope_type == "task" and item.scope_id == task.task_id and item.memory_type == "task_result":
            existing = item
            break
    memory = MemoryItem(
        memory_id=existing.memory_id if existing else new_id("mem"),
        memory_type="task_result",
        title=title,
        content=(output or task.result_summary or task.last_error or "")[:4000],
        confidence=0.75 if status == "succeeded" else 0.5,
        status="approved" if status == "succeeded" else "candidate",
        source_type="run",
        source_id=run.run_id,
        scope_type="task",
        scope_id=task.task_id,
        tags=["task", status, task.assigned_agent_id or "unassigned"],
        source_agent_id=task.assigned_agent_id,
        task_id=task.task_id,
        created_at=_now_iso(),
    )
    memory_repo.upsert(memory)
    record_memory_item_event(
        memory,
        event_type="task_result_recorded",
        created_by="ai",
        metadata={"status": status, "run_id": run.run_id},
    )


def _transition_task(task: Task, event: TaskEvent) -> Task:
    cur = _task_state(task.status)
    if not can_transition(cur, event):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_transition", "from": task.status.value, "event": event.value},
        )
    new_s = transition(cur, event)
    return _apply_task_status(task, TaskStatus(new_s.value))


def _new_plan(task: Task) -> ExecutionPlan:
    now = _now_iso()
    steps = [
        ExecutionStep(step_id=new_id("step"), kind="plan", status=ExecutionStepStatus.pending, created_at=now),
        ExecutionStep(step_id=new_id("step"), kind="execute", status=ExecutionStepStatus.pending, created_at=now),
        ExecutionStep(step_id=new_id("step"), kind="summarize", status=ExecutionStepStatus.pending, created_at=now),
    ]
    plan = ExecutionPlan(plan_id=new_id("plan"), task_id=task.task_id, created_at=now, updated_at=now, steps=steps)
    execution_plans_repo.upsert(plan)
    return plan


def _request_approval(task: Task, kind: ApprovalKind, reason: str, *, meta: dict[str, Any] | None = None) -> TaskApproval:
    approval = TaskApproval(
        approval_id=new_id("apr"),
        task_id=task.task_id,
        kind=kind,
        status=ApprovalStatus.pending,
        requested_at=_now_iso(),
        requested_by="system",
        reason=reason,
        meta=meta,
    )
    approvals_repo.upsert(approval)
    task2 = task.model_copy(update={"pending_approval_id": approval.approval_id, "updated_at": _now_iso()})
    # Use FSM transition into waiting_approval if possible; otherwise force.
    try:
        task2 = _transition_task(task2, TaskEvent.approval_requested)
    except HTTPException:
        task2 = task2.model_copy(update={"status": TaskStatus.waiting_approval, "updated_at": _now_iso()})
    tasks_repo.upsert(task2)
    _append_event(task.task_id, "approval_requested", reason, {"approval_id": approval.approval_id, "kind": kind.value, **(meta or {})})
    return approval


def get_execution_plan(task_id: str) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if not task.execution_plan_id:
        return {"task": task, "plan": None}
    plan = execution_plans_repo.get(task.execution_plan_id)
    return {"task": task, "plan": plan}


def _pilot_advance_and_maybe_execute(task: Task, approval_note: str | None) -> dict[str, Any]:
    # Create plan if missing.
    plan = execution_plans_repo.get(task.execution_plan_id) if task.execution_plan_id else None
    if not plan:
        plan = _new_plan(task)
        task = task.model_copy(update={"execution_plan_id": plan.plan_id, "updated_at": _now_iso()})
        tasks_repo.upsert(task)
        _append_event(task.task_id, "pilot_plan_created", "Pilot plan created", {"plan_id": plan.plan_id})

    # Find next pending step.
    next_step = next((s for s in plan.steps if s.status == ExecutionStepStatus.pending), None)
    if not next_step:
        return {"ok": True, "task": task, "plan": plan, "note": "no_pending_steps"}

    # Step 1: plan (no external calls; just persisted plan payload)
    if next_step.kind == "plan":
        payload = {
            "note": "Pilot mode: operator steps through plan → execute → summarize.",
            "operator_note": approval_note,
        }
        next_step = next_step.model_copy(update={"status": ExecutionStepStatus.done, "updated_at": _now_iso(), "payload": payload})
        plan2 = plan.model_copy(update={"steps": [next_step if s.step_id == next_step.step_id else s for s in plan.steps], "updated_at": _now_iso()})
        execution_plans_repo.upsert(plan2)
        _append_event(task.task_id, "pilot_step_done", "Pilot step done: plan", {"step_id": next_step.step_id})
        # Request approval for execute step.
        _request_approval(task, ApprovalKind.pilot_step, "Pilot step gate: execute", meta={"plan_id": plan2.plan_id, "step_kind": "execute"})
        task2 = tasks_repo.get(task.task_id) or task
        return {"ok": True, "task": task2, "plan": plan2, "pending_approval": True}

    # Step 2: execute (delegates to existing run execution)
    if next_step.kind == "execute":
        if not task.assigned_agent_id:
            raise HTTPException(status_code=400, detail="task_not_assigned")
        agent = agents_repo.get(task.assigned_agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="agent_not_found")
        # Start a run using the normal executor path.
        task2 = _transition_task(task, TaskEvent.run_started)
        tasks_repo.upsert(task2)
        run_id = new_id("run")
        task2 = ensure_task_correlation(task2)
        parent_run_id = resolve_parent_run_id(task2)
        run = Run(
            run_id=run_id,
            task_id=task.task_id,
            agent_id=agent.agent_id,
            status="running",
            started_at=_now_iso(),
            integration_path=None,
            correlation_id=task2.correlation_id,
            parent_run_id=parent_run_id,
            input_snapshot=build_run_input_snapshot(task2),
            environment_summary=build_environment_summary(task2, agent),
        )
        runs_repo.upsert(run)
        ensure_base_run_steps(run)
        task2 = task2.model_copy(update={"last_run_id": run_id, "updated_at": _now_iso()})
        tasks_repo.upsert(task2)
        _append_event(
            task.task_id,
            "run_started",
            "Pilot execute: run started",
            {"run_id": run_id, "agent_id": agent.agent_id, "parent_run_id": parent_run_id},
        )
        _append_run_log(run_id, 1, "info", "Pilot execute: run started", {"agent_id": agent.agent_id, "operator_note": approval_note})
        mark_run_step(run_id, "execute", "running", agent_id=agent.agent_id)
        agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.running, "last_heartbeat_at": _now_iso()}))

        adapter = agent.adapter_id or ("builtin_octopus" if agent.type == "builtin" else "unknown")
        res = execute_builtin_octopus(task2, run, agent) if agent.type == "builtin" or adapter == "builtin_octopus" else execute_via_local_bridge(task2, run, agent)
        _append_run_log(run_id, 2, "info", f"integration_path={res.integration_path}", res.meta)

        if res.ok and res.pending_handoff:
            # External handoff path: mark execute step done, but task waits for callback.
            next_step2 = next_step.model_copy(update={"status": ExecutionStepStatus.done, "updated_at": _now_iso(), "payload": {"pending_handoff": True, "integration_path": res.integration_path}})
            plan2 = plan.model_copy(update={"steps": [next_step2 if s.step_id == next_step.step_id else s for s in plan.steps], "updated_at": _now_iso()})
            execution_plans_repo.upsert(plan2)
            _append_event(task.task_id, "pilot_step_done", "Pilot step done: execute (handoff pending)", {"step_id": next_step.step_id, "run_id": run_id})
            # Task already transitions to waiting_approval in normal path; keep an approval record that points to callback completion.
            _request_approval(task2, ApprovalKind.external_handoff, "Waiting external completion for pilot execution", meta={"run_id": run_id, "integration_path": res.integration_path})
            return {"ok": True, "task": tasks_repo.get(task.task_id), "run": runs_repo.get(run_id), "plan": plan2, "pending_handoff": True}

        if res.ok:
            _append_run_log(run_id, 3, "info", "Pilot execute: succeeded", {"output_len": len(res.output or "")})
            run2 = run.model_copy(update={"status": "succeeded", "finished_at": _now_iso(), "integration_path": res.integration_path, "output_excerpt": (res.output or "")[:4000], "error": None})
            run2 = run2.model_copy(
                update={
                    "output_snapshot": {"status": "succeeded", "output": (res.output or "")[:4000]},
                    "environment_summary": build_environment_summary(task2, agent, integration_path=res.integration_path),
                }
            )
            runs_repo.upsert(run2)
            complete_run_timeline(run_id, succeeded=True)
            # Keep task running; summarize step will set final status.
            task3 = task2.model_copy(update={"result_summary": (res.output or "")[:2000], "result_payload": {"integration_path": res.integration_path, "meta": res.meta}, "last_error": None, "updated_at": _now_iso()})
            tasks_repo.upsert(task3)
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))

            next_step2 = next_step.model_copy(update={"status": ExecutionStepStatus.done, "updated_at": _now_iso(), "payload": {"run_id": run_id, "integration_path": res.integration_path}})
            plan2 = plan.model_copy(update={"steps": [next_step2 if s.step_id == next_step.step_id else s for s in plan.steps], "updated_at": _now_iso()})
            execution_plans_repo.upsert(plan2)
            _append_event(task.task_id, "pilot_step_done", "Pilot step done: execute", {"step_id": next_step.step_id, "run_id": run_id})
            _request_approval(task3, ApprovalKind.pilot_step, "Pilot step gate: summarize", meta={"plan_id": plan2.plan_id, "step_kind": "summarize"})
            return {"ok": True, "task": tasks_repo.get(task.task_id), "run": run2, "plan": plan2, "pending_approval": True}
        else:
            _append_run_log(run_id, 3, "error", f"Pilot execute: failed: {res.error}", res.meta)
            run2 = run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "integration_path": res.integration_path, "output_excerpt": (res.output or "")[:4000], "error": res.error})
            run2 = run2.model_copy(
                update={
                    "output_snapshot": {
                        "status": "failed",
                        "output": (res.output or "")[:4000],
                        "error": res.error,
                    },
                    "environment_summary": build_environment_summary(task2, agent, integration_path=res.integration_path),
                }
            )
            runs_repo.upsert(run2)
            complete_run_timeline(run_id, succeeded=False)
            task3 = _transition_task(task2, TaskEvent.task_failed)
            task3 = task3.model_copy(update={"status": TaskStatus.failed, "last_error": res.error, "updated_at": _now_iso()})
            tasks_repo.upsert(task3)
            _append_event(task.task_id, "task_failed", "Pilot execute failed", {"run_id": run_id, "error": res.error})
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.degraded, "last_heartbeat_at": _now_iso()}))
            next_step2 = next_step.model_copy(update={"status": ExecutionStepStatus.failed, "updated_at": _now_iso(), "payload": {"run_id": run_id, "error": res.error}})
            plan2 = plan.model_copy(update={"steps": [next_step2 if s.step_id == next_step.step_id else s for s in plan.steps], "updated_at": _now_iso()})
            execution_plans_repo.upsert(plan2)
            return {"ok": False, "task": task3, "run": run2, "plan": plan2, "error": res.error}

    # Step 3: summarize (finalizes task succeeded if execute succeeded)
    if next_step.kind == "summarize":
        summary = {
            "operator_note": approval_note,
            "result_summary": task.result_summary,
            "last_run_id": task.last_run_id,
        }
        next_step2 = next_step.model_copy(update={"status": ExecutionStepStatus.done, "updated_at": _now_iso(), "payload": summary})
        plan2 = plan.model_copy(update={"steps": [next_step2 if s.step_id == next_step.step_id else s for s in plan.steps], "updated_at": _now_iso()})
        execution_plans_repo.upsert(plan2)
        if task.last_run_id:
            mark_run_step(task.last_run_id, "summarize", "succeeded", output_ref=f"task:{task.task_id}:result_summary")
        # Finalize the audit step before exposing terminal task status.
        task2 = _transition_task(task, TaskEvent.task_succeeded)
        tasks_repo.upsert(task2)
        _append_event(task.task_id, "task_succeeded", "Pilot summarize: finalized success", {"plan_id": plan2.plan_id})
        return {"ok": True, "task": task2, "plan": plan2}

    return {"ok": True, "task": task, "plan": plan}


def approve_task(task_id: str, body: TaskApproveBody) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if not task.pending_approval_id:
        raise HTTPException(status_code=400, detail="no_pending_approval")
    approval = approvals_repo.get(task.pending_approval_id)
    if not approval or approval.task_id != task_id:
        raise HTTPException(status_code=404, detail="approval_not_found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="approval_not_pending")

    approval2 = approval.model_copy(update={"status": ApprovalStatus.approved, "decided_at": _now_iso(), "decided_by": "operator"})
    approvals_repo.upsert(approval2)
    _append_event(task_id, "approval_approved", body.note or "approved", {"approval_id": approval2.approval_id, "kind": approval2.kind.value})

    # Clear pending approval pointer before doing work (avoid double approval).
    task2 = task.model_copy(update={"pending_approval_id": None, "updated_at": _now_iso()})
    tasks_repo.upsert(task2)

    if approval2.kind == ApprovalKind.pilot_step:
        return _pilot_advance_and_maybe_execute(task2, body.note)

    if approval2.kind == ApprovalKind.policy_gate:
        # Record a short-lived override and start the run immediately (so approve is a true gate).
        override_until = build_policy_override_until(5)
        merged = dict(task2.result_payload or {})
        merged["policy_override_until"] = override_until
        task3 = task2.model_copy(update={"status": TaskStatus.assigned, "result_payload": merged, "updated_at": _now_iso()})
        tasks_repo.upsert(task3)
        _append_event(task_id, "policy_override_granted", "Operator approved policy gate; run unlocked", {"until": override_until})
        return run_task(task_id)

    # external_handoff: approval is recorded; actual completion arrives via callback.
    return {"ok": True, "task": task2, "approval": approval2}


def reject_task(task_id: str, body: TaskRejectBody) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if not task.pending_approval_id:
        raise HTTPException(status_code=400, detail="no_pending_approval")
    approval = approvals_repo.get(task.pending_approval_id)
    if not approval or approval.task_id != task_id:
        raise HTTPException(status_code=404, detail="approval_not_found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="approval_not_pending")

    approval2 = approval.model_copy(update={"status": ApprovalStatus.rejected, "decided_at": _now_iso(), "decided_by": "operator"})
    approvals_repo.upsert(approval2)
    _append_event(task_id, "approval_rejected", body.reason or "rejected", {"approval_id": approval2.approval_id, "kind": approval2.kind.value})

    # Mark task failed for safety (operator rejected).
    try:
        task2 = _transition_task(task, TaskEvent.task_failed)
    except HTTPException:
        task2 = task.model_copy(update={"status": TaskStatus.failed, "updated_at": _now_iso()})
    task2 = task2.model_copy(update={"pending_approval_id": None, "last_error": body.reason or "approval_rejected", "updated_at": _now_iso()})
    tasks_repo.upsert(task2)
    return {"ok": True, "task": task2, "approval": approval2}


def create_task(body: TaskCreateBody) -> Task:
    tid = new_id("task")
    task = Task(
        task_id=tid,
        title=body.title.strip(),
        description=body.description.strip() if body.description else None,
        execution_mode=body.execution_mode,
        queue_priority=body.queue_priority,
        status=TaskStatus.created,
        created_at=_now_iso(),
        updated_at=_now_iso(),
        correlation_id=new_id("corr"),
        source_task_id=body.source_task_id,
        max_recovery_attempts=get_default_max_recovery_attempts(),
    )
    tasks_repo.upsert(task)
    _append_event(tid, "task_created", "Task created", {"title": task.title, "queue_priority": task.queue_priority})
    _append_event(
        tid,
        "audit.task_created",
        "Audit: task created",
        {"title": task.title, "execution_mode": task.execution_mode, "queue_priority": task.queue_priority},
    )
    return task


def assign_task(task_id: str, body: TaskAssignBody) -> Task:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    agent = agents_repo.get(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    # Transition: allow agent_assigned from created (or queued if we add queue later)
    task = _transition_task(task, TaskEvent.agent_assigned)
    task = task.model_copy(update={"assigned_agent_id": body.agent_id, "updated_at": _now_iso()})
    tasks_repo.upsert(task)
    task_assignments_repo.upsert(
        TaskAssignment(
            assignment_id=new_id("asg"),
            task_id=task_id,
            agent_id=body.agent_id,
            assigned_at=_now_iso(),
            note=f"Assigned to {body.agent_id}",
        )
    )
    _append_event(
        task_id,
        "agent_assigned",
        f"Assigned to {body.agent_id}",
        {"agent_id": body.agent_id},
    )
    agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
    return task


def cancel_task(task_id: str) -> Task:
    """Cancel a task when FSM allows (Kanaloa / control-plane)."""
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    task = ensure_task_correlation(task)
    task2 = _transition_task(task, TaskEvent.task_cancelled)
    _append_event(
        task_id,
        "task_cancelled",
        "Task cancelled",
        {"source": "control_plane"},
    )
    return task2


def run_task(task_id: str) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    task = ensure_task_correlation(task)
    if task.status in (TaskStatus.queued, TaskStatus.running, TaskStatus.waiting_approval) and task.last_run_id:
        existing_run = runs_repo.get(task.last_run_id)
        if existing_run:
            task = reconcile_task_with_run(task, existing_run, source="duplicate_run_request")
        key = make_receipt_key("run_request", task.task_id, task.last_run_id, task.status.value)
        finalize_processed_receipt(
            "run_request",
            key,
            status="duplicate",
            task_id=task.task_id,
            run_id=task.last_run_id,
            correlation_id=task.correlation_id,
            result_ref=task.last_run_id,
            payload={"task_status": task.status.value},
        )
        _append_event(
            task_id,
            "duplicate_run_request",
            f"Duplicate run request ignored while task is {task.status.value}",
            {"run_id": task.last_run_id, "status": task.status.value},
        )
        return {
            "ok": True,
            "duplicate_request": True,
            "task": task,
            "run": existing_run,
        }
    if not task.assigned_agent_id:
        raise HTTPException(status_code=400, detail="task_not_assigned")

    agent = agents_repo.get(task.assigned_agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    # Mode enforcement: direct_agent must use an external adapter path.
    if task.execution_mode == "direct_agent" and agent.type != "external":
        raise HTTPException(status_code=400, detail="direct_agent_requires_external_agent")

    # Policy gate (opt-in): enforce only non-draft policies.
    decision = evaluate_task_run(task, agent)
    _append_event(
        task_id,
        "policy_evaluated",
        "Policy evaluated for run",
        {
            "allow": decision.allow,
            "require_approval": decision.require_approval,
            "reason": decision.reason,
            "policy_id": decision.policy.policy_id if decision.policy else None,
            "queue_priority": task.queue_priority,
        },
    )
    if not decision.allow:
        raise HTTPException(status_code=403, detail="policy_denied")
    if decision.require_approval:
        approval = _request_approval(
            task,
            ApprovalKind.policy_gate,
            decision.reason or "Policy requires confirmation",
            meta={"policy_id": decision.policy.policy_id if decision.policy else None, "action": "start_run"},
        )
        return {"ok": True, "pending_approval": True, "approval": approval, "task": tasks_repo.get(task_id)}

    # Pilot mode: create plan + require operator approval to advance steps.
    if task.execution_mode == "pilot":
        plan = execution_plans_repo.get(task.execution_plan_id) if task.execution_plan_id else None
        if not plan:
            plan = _new_plan(task)
            task = task.model_copy(update={"execution_plan_id": plan.plan_id, "updated_at": _now_iso()})
            tasks_repo.upsert(task)
            _append_event(task_id, "pilot_plan_created", "Pilot plan created", {"plan_id": plan.plan_id})
        approval = _request_approval(task, ApprovalKind.pilot_step, "Pilot step gate: plan", meta={"plan_id": plan.plan_id, "step_kind": "plan"})
        return {"ok": True, "pending_approval": True, "approval": approval, "task": tasks_repo.get(task_id), "plan": plan}

    request_key = make_receipt_key(
        "run_request",
        task.task_id,
        str(task.retry_count),
        task.assigned_agent_id,
        task.execution_mode,
    )
    claimed, existing_receipt = claim_processed_receipt(
        "run_request",
        request_key,
        task_id=task.task_id,
        run_id=task.last_run_id,
        correlation_id=task.correlation_id,
        payload={"task_status": task.status.value},
    )
    if not claimed:
        existing_run = (
            runs_repo.get(existing_receipt.result_ref)
            if existing_receipt.result_ref
            else runs_repo.get(task.last_run_id)
            if task.last_run_id
            else None
        )
        if existing_run:
            reconcile_task_with_run(tasks_repo.get(task_id) or task, existing_run, source="claimed_duplicate_run_request")
        _append_event(
            task_id,
            "duplicate_run_request",
            "Duplicate run request ignored by claim-first receipt guard",
            {
                "receipt_status": existing_receipt.status,
                "run_id": existing_run.run_id if existing_run else task.last_run_id,
                "queue_priority": task.queue_priority,
            },
        )
        return {
            "ok": True,
            "duplicate_request": True,
            "task": tasks_repo.get(task_id) or task,
            "run": existing_run,
        }

    # Queue-based execution (milestone B): enqueue run and return immediately.
    # Worker will emit run_started/logs/events shortly after.
    try:
        task = task.model_copy(update={"status": TaskStatus.queued, "updated_at": _now_iso()})
        tasks_repo.upsert(task)
        run = enqueue_run(task_id, agent.agent_id)
        task = task.model_copy(update={"last_run_id": run.run_id, "updated_at": _now_iso()})
        tasks_repo.upsert(task)
        _append_event(
            task_id,
            "audit.run_requested",
            "Audit: run requested",
            {"run_id": run.run_id, "agent_id": agent.agent_id},
        )
        finalize_processed_receipt(
            "run_request",
            request_key,
            status="completed",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=task.correlation_id,
            result_ref=run.run_id,
            payload={"queued": True},
        )
        return {"ok": True, "queued": True, "task": task, "run": run}
    except Exception as exc:
        finalize_processed_receipt(
            "run_request",
            request_key,
            status="failed",
            task_id=task.task_id,
            run_id=task.last_run_id,
            correlation_id=task.correlation_id,
            payload={"error": str(exc)},
        )
        raise


def retry_task(task_id: str) -> Task:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    task = ensure_task_correlation(task)
    if task.last_run_id:
        last_run = runs_repo.get(task.last_run_id)
        if last_run and last_run.status in {"succeeded", "failed"}:
            task = reconcile_task_with_run(task, last_run, source="retry_request_preflight")
    if task.status == TaskStatus.assigned and task.retry_count > 0:
        _append_event(
            task_id,
            "duplicate_retry_request",
            "Duplicate retry request ignored",
            {"retry_count": task.retry_count},
        )
        finalize_processed_receipt(
            "retry_request",
            make_receipt_key("retry_request", task.task_id, task.last_run_id, str(task.retry_count)),
            status="duplicate",
            task_id=task.task_id,
            run_id=task.last_run_id,
            correlation_id=task.correlation_id,
            result_ref=task.task_id,
            payload={"retry_count": task.retry_count},
        )
        return task
    cur = _task_state(task.status)
    if not can_transition(cur, TaskEvent.retry_requested):
        raise HTTPException(
            status_code=400,
            detail={"error": "retry_not_allowed", "from": task.status.value},
        )
    request_key = make_receipt_key(
        "retry_request",
        task.task_id,
        task.last_run_id,
        str(task.retry_count + 1),
    )
    claimed, existing_receipt = claim_processed_receipt(
        "retry_request",
        request_key,
        task_id=task.task_id,
        run_id=task.last_run_id,
        correlation_id=task.correlation_id,
        payload={"task_status": task.status.value},
    )
    if not claimed:
        _append_event(
            task_id,
            "duplicate_retry_request",
            "Duplicate retry request ignored by claim-first receipt guard",
            {"receipt_status": existing_receipt.status, "retry_count": task.retry_count},
        )
        return task
    try:
        parent_run_id = resolve_parent_run_id(task)
        task = _transition_task(task, TaskEvent.retry_requested)
        task = task.model_copy(
            update={
                "retry_count": task.retry_count + 1,
                "last_error": None,
                "updated_at": _now_iso(),
                "needs_attention": False,
                "attention_reason": None,
            }
        )
        tasks_repo.upsert(task)
        _append_event(
            task_id,
            "retry_requested",
            f"Retry scheduled (count={task.retry_count})",
            {"retry_count": task.retry_count, "parent_run_id": parent_run_id},
        )
        if task.assigned_agent_id:
            agent = agents_repo.get(task.assigned_agent_id)
            if agent:
                agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
        finalize_processed_receipt(
            "retry_request",
            request_key,
            status="completed",
            task_id=task.task_id,
            run_id=task.last_run_id,
            correlation_id=task.correlation_id,
            result_ref=task.task_id,
            payload={"retry_count": task.retry_count},
        )
        return task
    except Exception as exc:
        finalize_processed_receipt(
            "retry_request",
            request_key,
            status="failed",
            task_id=task.task_id,
            run_id=task.last_run_id,
            correlation_id=task.correlation_id,
            payload={"error": str(exc)},
        )
        raise


def mark_failed(task_id: str, body: TaskFailBody) -> Task:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    cur = _task_state(task.status)
    if cur == TaskState.succeeded:
        raise HTTPException(status_code=400, detail="cannot_fail_succeeded_task")
    # Force failed from running/assigned/created etc. for operator recovery
    task = task.model_copy(
        update={
            "status": TaskStatus.failed,
            "last_error": body.reason,
            "updated_at": _now_iso(),
        }
    )
    tasks_repo.upsert(task)
    if task.last_run_id:
        run = runs_repo.get(task.last_run_id)
        if run and run.status not in {"succeeded", "failed"}:
            runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": body.reason}))
        if run:
            complete_run_timeline(task.last_run_id, succeeded=False)
    _append_event(task_id, "operator_mark_failed", body.reason, None)
    _append_watchdog_event(
        "operator_mark_failed",
        f"Operator marked task {task_id} failed: {body.reason}",
        "warn",
        task_id=task_id,
        agent_id=task.assigned_agent_id,
        recovery_hint="Retry after reviewing the task timeline and run logs.",
    )
    return task


def _build_supervision_summary(
    task: Task,
    runs: list[Run],
    watchdog_events: list[WatchdogEvent],
    last_run: Run | None,
) -> dict[str, Any]:
    fixer_events = sum(
        1
        for e in watchdog_events
        if "fixer" in (e.source or "").lower() or "fixer" in (e.issue_class or "").lower()
    )
    completion_hint = "unknown"
    if last_run and last_run.integration_path:
        path = last_run.integration_path.lower()
        if "handoff" in path or "manual" in path:
            completion_hint = "handoff_callback"
        elif path in {"http_agent", "cli_agent", "bridge_sync"} or "bridge" in path:
            completion_hint = "bridge_sync"
    elif task.status.value == "waiting_approval":
        completion_hint = "handoff_callback"

    duration_label: str | None = None
    if task.created_at and last_run:
        end = last_run.finished_at or last_run.started_at
        if end:
            try:
                start_dt = datetime.fromisoformat(task.created_at.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                secs = max(0, int((end_dt - start_dt).total_seconds()))
                if secs < 60:
                    duration_label = f"{secs}s"
                else:
                    duration_label = f"{secs // 60}m {secs % 60}s"
            except ValueError:
                duration_label = None

    return {
        "recovery_attempt_count": task.recovery_attempt_count,
        "watchdog_events_count": len(watchdog_events),
        "fixer_related_events": fixer_events,
        "completion_mode_hint": completion_hint,
        "duration_label": duration_label,
        "task_status": task.status.value,
    }


def get_timeline(
    task_id: str,
    events_limit: int = DEFAULT_TIMELINE_EVENTS_LIMIT,
    logs_limit: int = DEFAULT_TIMELINE_LOGS_LIMIT,
) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    events, events_total = list_events_for_task(task_id, tail=events_limit)
    runs = [r for r in runs_repo.list() if r.task_id == task_id]
    runs.sort(key=lambda x: x.finished_at or x.started_at or x.queued_at or "", reverse=True)
    run_ids = {r.run_id for r in runs}
    logs, logs_total = list_logs_for_runs(run_ids, tail=logs_limit)
    assignments = [a for a in task_assignments_repo.list() if a.task_id == task_id]
    assignments.sort(key=lambda x: x.assigned_at, reverse=True)
    watchdog_events = [e for e in watchdog_events_repo.list() if e.task_id == task_id]
    watchdog_events.sort(key=lambda x: x.created_at)
    last_run = runs[0] if runs else None
    return {
        "version": "2.0.0",
        "task": task,
        "assignments": assignments,
        "events": events,
        "runs": runs,
        "run_logs": logs,
        "watchdog_events": watchdog_events,
        "events_total": events_total,
        "run_logs_total": logs_total,
        "orchestrator_context": find_master_context_for_platform_task(task_id),
        "supervision_summary": _build_supervision_summary(task, runs, watchdog_events, last_run),
        "version": "2.0.0",
    }


def bridge_complete(body: BridgeCompleteBody) -> dict[str, Any]:
    """Complete a run from Local Bridge async path (honest callback)."""
    b = body
    task = tasks_repo.get(b.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    task = ensure_task_correlation(task)
    run = runs_repo.get(b.run_id)
    if not run or run.task_id != b.task_id:
        raise HTTPException(status_code=404, detail="run_not_found")
    agent = agents_repo.get(task.assigned_agent_id) if task.assigned_agent_id else None
    callback_key = make_receipt_key(
        "bridge_callback",
        b.task_id,
        b.run_id,
        b.status,
        b.integration_path or "bridge_callback",
        b.error or "",
        (b.output or "")[:120],
    )
    claimed, existing_receipt = claim_processed_receipt(
        "bridge_callback",
        callback_key,
        task_id=task.task_id,
        run_id=run.run_id,
        correlation_id=task.correlation_id,
        payload={"callback_status": b.status, "integration_path": b.integration_path},
    )
    if not claimed:
        _append_event(
            b.task_id,
            "duplicate_callback",
            "Duplicate bridge callback ignored",
            {"run_id": b.run_id, "status": b.status, "receipt_status": existing_receipt.status},
        )
        return {"ok": True, "duplicate_callback": True, "task": task, "run": run}
    if run.status in ("succeeded", "failed"):
        complete_run_timeline(run.run_id, succeeded=run.status == "succeeded")
        _append_event(
            b.task_id,
            "late_callback",
            "Late bridge callback recorded without changing final state",
            {"run_id": b.run_id, "status": b.status, "integration_path": b.integration_path},
        )
        append_watchdog_issue(
            "late_callback",
            f"Late callback received for finished run {b.run_id}",
            severity="warn",
            task=task,
            run_id=run.run_id,
            raw_error=b.error,
            source="watchdog",
            issue_status="resolved",
            suggested_action="audit_only",
        )
        finalize_processed_receipt(
            "bridge_callback",
            callback_key,
            status="late_callback",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=task.correlation_id,
            result_ref=run.run_id,
            payload={"callback_status": b.status, "integration_path": b.integration_path, "late": True},
        )
        return {"ok": True, "late_callback": True, "task": task, "run": run}

    allowed_sources = []
    if agent and agent.control_plane and agent.control_plane.callback_source_allowlist:
        allowed_sources = [item for item in agent.control_plane.callback_source_allowlist if item]
    if allowed_sources and (b.integration_path or "bridge_callback") not in allowed_sources:
        task = mark_task_attention(
            task,
            "Bridge callback rejected by source boundary; operator review is required",
            source="watchdog",
        )
        _append_event(
            b.task_id,
            "callback_rejected",
            "Bridge callback rejected by source boundary",
            {
                "run_id": b.run_id,
                "integration_path": b.integration_path,
                "allowed_sources": allowed_sources,
            },
        )
        append_watchdog_issue(
            "callback_source_rejected",
            f"Callback source rejected for run {b.run_id}",
            severity="warn",
            task=task,
            run_id=run.run_id,
            raw_error=b.integration_path,
            source="watchdog",
            issue_status="escalated",
            suggested_action="defer_to_human",
            recovery_hint="The callback integration_path is outside the configured allowlist.",
            parent_run_id=run.parent_run_id,
        )
        append_task_event(
            task.task_id,
            "escalation_opened",
            "Bridge callback rejection escalated to human review",
            correlation_id=task.correlation_id,
            payload={"issue_class": "callback_source_rejected", "parent_run_id": run.parent_run_id},
        )
        upsert_advisor_suggestion(
            suggestion_type="recovery_suggestion",
            target_type="task",
            target_id=task.task_id,
            issue_class="callback_source_rejected",
            title="Review callback allowlist or bridge route",
            summary="A bridge callback was rejected by the configured source boundary.",
            rationale=(
                f"Task {task.task_id} received integration_path "
                f"{b.integration_path or 'bridge_callback'}, but the agent only allows {allowed_sources}."
            ),
            recommended_action="Check callback_source_allowlist and the bridge handoff route before retrying.",
            evidence_refs=[
                {"kind": "task", "id": task.task_id},
                {"kind": "run", "id": run.run_id},
            ],
            severity="warning",
            requires_confirmation=True,
            correlation_id=task.correlation_id,
            source_task_id=task.task_id,
            source_run_id=run.run_id,
        )
        finalize_processed_receipt(
            "bridge_callback",
            callback_key,
            status="rejected",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=task.correlation_id,
            result_ref=run.run_id,
            payload={"callback_status": b.status, "integration_path": b.integration_path, "allowed_sources": allowed_sources},
        )
        return {"ok": False, "rejected": True, "task": task, "run": run}

    try:
        if b.status == "succeeded":
            run = run.model_copy(
                update={
                    "status": "succeeded",
                    "finished_at": _now_iso(),
                    "integration_path": b.integration_path or "bridge_callback",
                    "output_excerpt": (b.output or "")[:4000],
                    "error": None,
                    "output_snapshot": {
                        "status": "succeeded",
                        "output": (b.output or "")[:4000],
                        "integration_path": b.integration_path or "bridge_callback",
                    },
                    "callback_summary": {
                        "received_at": _now_iso(),
                        "status": b.status,
                        "integration_path": b.integration_path or "bridge_callback",
                    },
                }
            )
            runs_repo.upsert(run)
            complete_run_timeline(run.run_id, succeeded=True)
            try:
                task2 = _transition_task(task, TaskEvent.task_succeeded)
            except HTTPException:
                task2 = task.model_copy(update={"status": TaskStatus.succeeded, "updated_at": _now_iso()})
            task2 = task2.model_copy(
                update={
                    "result_summary": (b.output or "")[:2000],
                    "result_payload": {
                        "integration_path": b.integration_path or "bridge_callback",
                        "output": (b.output or "")[:4000],
                        "callback_summary": {
                            "received_at": _now_iso(),
                            "status": b.status,
                            "integration_path": b.integration_path or "bridge_callback",
                        },
                    },
                    "last_error": None,
                    "needs_attention": False,
                    "attention_reason": None,
                    "updated_at": _now_iso(),
                }
            )
            tasks_repo.upsert(task2)
            _append_event(b.task_id, "task_succeeded", "Bridge reported success", {"run_id": b.run_id})
            _upsert_task_memory(task2, run, b.output, status="succeeded")
            finalize_processed_receipt(
                "bridge_callback",
                callback_key,
                status="completed",
                task_id=task.task_id,
                run_id=run.run_id,
                correlation_id=task.correlation_id,
                result_ref=run.run_id,
                payload={"callback_status": b.status, "task_status": task2.status.value},
            )
            if task.assigned_agent_id:
                agent = agents_repo.get(task.assigned_agent_id)
                if agent:
                    agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
            return {"ok": True, "task": task2, "run": run}

        run = run.model_copy(
            update={
                "status": "failed",
                "finished_at": _now_iso(),
                "integration_path": b.integration_path or "bridge_callback",
                "error": b.error,
                "output_excerpt": (b.output or "")[:4000],
                "output_snapshot": {
                    "status": "failed",
                    "output": (b.output or "")[:4000],
                    "error": b.error,
                    "integration_path": b.integration_path or "bridge_callback",
                },
                "callback_summary": {
                    "received_at": _now_iso(),
                    "status": b.status,
                    "integration_path": b.integration_path or "bridge_callback",
                    "error": b.error,
                },
            }
        )
        runs_repo.upsert(run)
        complete_run_timeline(run.run_id, succeeded=False)
        try:
            task2 = _transition_task(task, TaskEvent.task_failed)
        except HTTPException:
            task2 = task.model_copy(update={"status": TaskStatus.failed, "updated_at": _now_iso()})
        task2 = task2.model_copy(
            update={
                "last_error": b.error,
                "result_payload": {
                    "integration_path": b.integration_path or "bridge_callback",
                    "output": (b.output or "")[:4000],
                    "error": b.error,
                    "callback_summary": {
                        "received_at": _now_iso(),
                        "status": b.status,
                        "integration_path": b.integration_path or "bridge_callback",
                        "error": b.error,
                    },
                },
                "updated_at": _now_iso(),
            }
        )
        tasks_repo.upsert(task2)
        _append_event(b.task_id, "task_failed", "Bridge reported failure", {"run_id": b.run_id})
        _upsert_task_memory(task2, run, b.output or b.error, status="failed")
        finalize_processed_receipt(
            "bridge_callback",
            callback_key,
            status="completed",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=task.correlation_id,
            result_ref=run.run_id,
            payload={"callback_status": b.status, "task_status": task2.status.value},
        )
        if task.assigned_agent_id:
            agent = agents_repo.get(task.assigned_agent_id)
            if agent:
                agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.degraded, "last_heartbeat_at": _now_iso()}))
        _append_watchdog_event(
            "bridge_reported_failure",
            f"Bridge reported task {b.task_id} failed: {b.error}",
            "error",
            task_id=b.task_id,
            agent_id=task.assigned_agent_id,
            recovery_hint="Retry the task after checking the bridge handoff file or external adapter output.",
        )
        return {"ok": False, "task": task2, "run": run}
    except Exception as exc:
        finalize_processed_receipt(
            "bridge_callback",
            callback_key,
            status="failed",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=task.correlation_id,
            result_ref=run.run_id,
            payload={"callback_status": b.status, "error": str(exc)},
        )
        raise


def register_local_bridge_agent(body: LocalBridgeRegisterBody) -> LocalBridgeAgentState:
    now = body.last_seen_at or _now_iso()
    existing = local_bridge_repo.get(body.agent_id)
    state = LocalBridgeAgentState(
        state_id=body.agent_id,
        bridge_id=body.bridge_id,
        agent_id=body.agent_id,
        display_name=body.display_name,
        adapter_id=body.adapter_id,
        capabilities=body.capabilities,
        workspace_path=body.workspace_path,
        status=body.status,
        registered_at=existing.registered_at if existing else now,
        last_seen_at=now,
        last_task_id=existing.last_task_id if existing else None,
        last_run_id=existing.last_run_id if existing else None,
        last_result_status=existing.last_result_status if existing else None,
        last_error=existing.last_error if existing else None,
    )
    local_bridge_repo.upsert(state)

    agent = agents_repo.get(body.agent_id)
    if agent:
        agents_repo.upsert(
            agent.model_copy(
                update={
                    "display_name": body.display_name,
                    "adapter_id": body.adapter_id,
                    "last_heartbeat_at": now,
                    "status": (
                        AgentStatus.idle
                        if body.status in ("online", "idle")
                        else AgentStatus.running
                        if body.status == "running"
                        else AgentStatus.degraded
                        if body.status == "degraded"
                        else AgentStatus.offline
                    ),
                }
            )
        )
    else:
        agents_repo.upsert(
            Agent(
                agent_id=body.agent_id,
                display_name=body.display_name,
                type="external",
                status=(
                    AgentStatus.idle
                    if body.status in ("online", "idle")
                    else AgentStatus.running
                    if body.status == "running"
                    else AgentStatus.degraded
                    if body.status == "degraded"
                    else AgentStatus.offline
                ),
                capabilities=AgentCapabilities.model_validate(body.capabilities),
                last_heartbeat_at=now,
                adapter_id=body.adapter_id,
            )
        )

    _append_watchdog_event(
        "bridge_agent_registered",
        f"Local bridge registered {body.agent_id} ({body.adapter_id})",
        "info",
        agent_id=body.agent_id,
        recovery_hint="If the agent stops appearing, re-register it or inspect the Local Bridge service.",
    )
    return state


def local_bridge_result(body: LocalBridgeResultBody) -> dict[str, Any]:
    task = tasks_repo.get(body.task_id)
    if task and task.assigned_agent_id and body.agent_id != task.assigned_agent_id:
        raise HTTPException(status_code=400, detail="callback_agent_mismatch")
    result = bridge_complete(
        BridgeCompleteBody(
            task_id=body.task_id,
            run_id=body.run_id,
            status=body.status,
            output=body.output,
            error=body.error,
            integration_path=body.integration_path,
        )
    )
    accepted_callback = not any(
        (
            result.get("rejected"),
            result.get("duplicate_callback"),
            result.get("late_callback"),
        )
    )
    if accepted_callback:
        _update_local_bridge_callback_state(body)
        run_logs = [l for l in run_logs_repo.list() if l.run_id == body.run_id]
        next_seq = (max((l.seq for l in run_logs), default=0) + 1) if run_logs else 1
        _append_run_log(
            body.run_id,
            next_seq,
            "info" if body.status == "succeeded" else "error",
            f"Local bridge submitted {body.status}",
            body.result_meta,
        )
    return result

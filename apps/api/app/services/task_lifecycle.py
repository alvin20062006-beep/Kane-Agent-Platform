from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from ..executor import execute_builtin_octopus, execute_via_local_bridge
from ..fsm import TaskEvent, TaskState, can_transition, transition
from ..id_utils import new_id
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


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _task_state(ts: TaskStatus) -> TaskState:
    return TaskState(ts.value)


def _apply_task_status(task: Task, new_status: TaskStatus) -> Task:
    return task.model_copy(update={"status": new_status, "updated_at": _now_iso()})


def _append_event(task_id: str, typ: str, message: str | None, payload: dict[str, Any] | None = None) -> TaskEventRecord:
    ev = TaskEventRecord(
        event_id=new_id("evt"),
        task_id=task_id,
        type=typ,
        message=message,
        payload=payload,
        created_at=_now_iso(),
    )
    task_events_repo.upsert(ev)
    return ev


def _append_run_log(run_id: str, seq: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
    line = RunLogLine(
        log_id=new_id("log"),
        run_id=run_id,
        seq=seq,
        level=level,  # type: ignore[arg-type]
        message=message,
        meta=meta,
        created_at=_now_iso(),
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
    ev = WatchdogEvent(
        event_id=new_id("wd"),
        type=typ,
        message=message,
        created_at=_now_iso(),
        severity=severity,  # type: ignore[arg-type]
        task_id=task_id,
        agent_id=agent_id,
        recovery_hint=recovery_hint,
    )
    watchdog_events_repo.upsert(ev)
    # Best-effort: notify enabled channels (beta)
    try:
        deliver_watchdog_event(ev.model_dump())
    except Exception:
        pass


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
        run = Run(run_id=run_id, task_id=task.task_id, agent_id=agent.agent_id, status="running", started_at=_now_iso(), integration_path=None)
        runs_repo.upsert(run)
        task2 = task2.model_copy(update={"last_run_id": run_id, "updated_at": _now_iso()})
        tasks_repo.upsert(task2)
        _append_event(task.task_id, "run_started", "Pilot execute: run started", {"run_id": run_id, "agent_id": agent.agent_id})
        _append_run_log(run_id, 1, "info", "Pilot execute: run started", {"agent_id": agent.agent_id, "operator_note": approval_note})
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
            runs_repo.upsert(run2)
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
            runs_repo.upsert(run2)
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
        # finalize task
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
        status=TaskStatus.created,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    tasks_repo.upsert(task)
    _append_event(tid, "task_created", "Task created", {"title": task.title})
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


def run_task(task_id: str) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.status == TaskStatus.running:
        raise HTTPException(status_code=400, detail="task_already_running")
    if task.status == TaskStatus.waiting_approval:
        raise HTTPException(status_code=400, detail="task_waiting_approval_use_approve_or_callback")
    if not task.assigned_agent_id:
        raise HTTPException(status_code=400, detail="task_not_assigned")

    agent = agents_repo.get(task.assigned_agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    # Mode enforcement: direct_agent must use an external adapter path.
    if task.execution_mode == "direct_agent" and agent.type != "external":
        raise HTTPException(status_code=400, detail="direct_agent_requires_external_agent")

    # Policy gate (opt-in): enforce only non-mock policies.
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

    # Queue-based execution (milestone B): enqueue run and return immediately.
    # Worker will emit run_started/logs/events shortly after.
    task = task.model_copy(update={"status": TaskStatus.queued, "updated_at": _now_iso()})
    tasks_repo.upsert(task)
    run = enqueue_run(task_id, agent.agent_id)
    task = task.model_copy(update={"last_run_id": run.run_id, "updated_at": _now_iso()})
    tasks_repo.upsert(task)
    return {"ok": True, "queued": True, "task": task, "run": run}


def retry_task(task_id: str) -> Task:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    cur = _task_state(task.status)
    if not can_transition(cur, TaskEvent.retry_requested):
        raise HTTPException(
            status_code=400,
            detail={"error": "retry_not_allowed", "from": task.status.value},
        )
    task = _transition_task(task, TaskEvent.retry_requested)
    task = task.model_copy(
        update={
            "retry_count": task.retry_count + 1,
            "last_error": None,
            "updated_at": _now_iso(),
        }
    )
    tasks_repo.upsert(task)
    _append_event(
        task_id,
        "retry_requested",
        f"Retry scheduled (count={task.retry_count})",
        {"retry_count": task.retry_count},
    )
    if task.assigned_agent_id:
        agent = agents_repo.get(task.assigned_agent_id)
        if agent:
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
    return task


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


def get_timeline(task_id: str) -> dict[str, Any]:
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    events = [e for e in task_events_repo.list() if e.task_id == task_id]
    events.sort(key=lambda x: x.created_at)
    runs = [r for r in runs_repo.list() if r.task_id == task_id]
    runs.sort(key=lambda x: x.started_at, reverse=True)
    run_ids = {r.run_id for r in runs}
    logs = [l for l in run_logs_repo.list() if l.run_id in run_ids]
    logs.sort(key=lambda x: (x.run_id, x.seq))
    assignments = [a for a in task_assignments_repo.list() if a.task_id == task_id]
    assignments.sort(key=lambda x: x.assigned_at, reverse=True)
    return {
        "beta": True,
        "task": task,
        "assignments": assignments,
        "events": events,
        "runs": runs,
        "run_logs": logs,
    }


def bridge_complete(body: BridgeCompleteBody) -> dict[str, Any]:
    """Complete a run from Local Bridge async path (honest callback)."""
    b = body
    task = tasks_repo.get(b.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    run = runs_repo.get(b.run_id)
    if not run or run.task_id != b.task_id:
        raise HTTPException(status_code=404, detail="run_not_found")

    if b.status == "succeeded":
        run = run.model_copy(
            update={
                "status": "succeeded",
                "finished_at": _now_iso(),
                "integration_path": b.integration_path or "bridge_callback",
                "output_excerpt": (b.output or "")[:4000],
                "error": None,
            }
        )
        runs_repo.upsert(run)
        # task may still be running — force success path
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
                },
                "last_error": None,
                "updated_at": _now_iso(),
            }
        )
        tasks_repo.upsert(task2)
        _append_event(b.task_id, "task_succeeded", "Bridge reported success", {"run_id": b.run_id})
        _upsert_task_memory(task2, run, b.output, status="succeeded")
        if task.assigned_agent_id:
            agent = agents_repo.get(task.assigned_agent_id)
            if agent:
                agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
        return {"ok": True, "task": task2, "run": run}
    else:
        run = run.model_copy(
            update={
                "status": "failed",
                "finished_at": _now_iso(),
                "integration_path": b.integration_path or "bridge_callback",
                "error": b.error,
                "output_excerpt": (b.output or "")[:4000],
            }
        )
        runs_repo.upsert(run)
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
                },
                "updated_at": _now_iso(),
            }
        )
        tasks_repo.upsert(task2)
        _append_event(b.task_id, "task_failed", "Bridge reported failure", {"run_id": b.run_id})
        _upsert_task_memory(task2, run, b.output or b.error, status="failed")
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
    existing = local_bridge_repo.get(body.agent_id)
    if existing:
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

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..executor import execute_builtin_octopus, execute_via_local_bridge
from ..fsm import TaskEvent
from ..id_utils import new_id
from ..models import AgentStatus, Run, Task, TaskStatus
from ..settings_env import (
    get_worker_max_concurrent_runs,
    get_worker_per_agent_serialization_enabled,
    get_worker_poll_interval_seconds,
)
from ..store.repositories import agents_repo, run_logs_repo, runs_repo, task_events_repo, tasks_repo
from .runtime_audit import (
    append_task_event,
    append_watchdog_issue,
    build_environment_summary,
    build_run_input_snapshot,
    ensure_task_correlation,
    mark_task_attention,
    now_iso,
    resolve_parent_run_id,
)


def _now_iso() -> str:
    return now_iso()


def _append_event(task_id: str, typ: str, message: str | None, payload: dict[str, Any] | None = None) -> None:
    task = tasks_repo.get(task_id)
    append_task_event(
        task_id,
        typ,
        message,
        correlation_id=task.correlation_id if task else None,
        payload=payload,
    )


def _append_run_log(run_id: str, seq: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
    run = runs_repo.get(run_id)
    run_logs_repo.upsert(
        run_logs_repo.model.model_validate(
            {
                "log_id": new_id("log"),
                "run_id": run_id,
                "seq": seq,
                "level": level,
                "message": message,
                "meta": meta,
                "created_at": _now_iso(),
                "correlation_id": run.correlation_id if run else None,
            }
        )
    )


_PRIORITY_ORDER = {"urgent": 3, "high": 2, "normal": 1, "low": 0}


class WorkerState:
    def __init__(self) -> None:
        self.started_at = _now_iso()
        self.last_tick_at: str | None = None
        self.last_run_id: str | None = None
        self.last_error: str | None = None
        self.running = False


_STATE = WorkerState()
_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()
_ACTIVE_RUNS: set[str] = set()


def _scheduler_config() -> dict[str, Any]:
    return {
        "max_concurrent_runs": get_worker_max_concurrent_runs(),
        "per_agent_serialization": get_worker_per_agent_serialization_enabled(),
        "poll_interval_seconds": get_worker_poll_interval_seconds(),
    }


def get_worker_state() -> dict[str, Any]:
    return {
        "started_at": _STATE.started_at,
        "last_tick_at": _STATE.last_tick_at,
        "last_run_id": _STATE.last_run_id,
        "last_error": _STATE.last_error,
        "running": _STATE.running,
        "active_run_ids": sorted(_ACTIVE_RUNS),
        "scheduler": _scheduler_config(),
    }


def start_worker_thread() -> None:
    global _THREAD
    existing: threading.Thread | None = None
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            if _STATE.running:
                return
            existing = _THREAD
    if existing:
        existing.join(timeout=max(get_worker_poll_interval_seconds() * 2, 0.5))
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            if _STATE.running:
                return
            _THREAD = None
        _STATE.running = True
        _THREAD = threading.Thread(target=_loop, name="octopus-worker", daemon=True)
        _THREAD.start()


def stop_worker_thread() -> None:
    global _THREAD
    thread: threading.Thread | None = None
    with _LOCK:
        _STATE.running = False
        thread = _THREAD
    if thread and thread.is_alive():
        thread.join(timeout=max(get_worker_poll_interval_seconds() * 2, 0.5))
    with _LOCK:
        if _THREAD is thread and (thread is None or not thread.is_alive()):
            _THREAD = None


def enqueue_run(task_id: str, agent_id: str) -> Run:
    """
    Create a pending run and let the background worker execute it.
    Persisted in runs.json; status=pending means queued.
    """
    task = tasks_repo.get(task_id)
    if not task:
        raise ValueError("task_not_found")
    task = ensure_task_correlation(task)
    parent_run_id = resolve_parent_run_id(task)
    run_id = new_id("run")
    run = Run(
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        status="pending",
        queued_at=_now_iso(),
        integration_path=None,
        correlation_id=task.correlation_id,
        parent_run_id=parent_run_id,
        input_snapshot=build_run_input_snapshot(task),
    )
    runs_repo.upsert(run)
    tasks_repo.upsert(task.model_copy(update={"last_run_id": run_id, "updated_at": _now_iso()}))
    start_worker_thread()
    _append_event(
        task_id,
        "run_queued",
        "Run queued",
        {
            "run_id": run_id,
            "agent_id": agent_id,
            "parent_run_id": parent_run_id,
            "queue_priority": task.queue_priority,
        },
    )
    _append_run_log(run_id, 1, "info", "Run queued", {"agent_id": agent_id, "queue_priority": task.queue_priority})
    return run


def _loop() -> None:
    poll = get_worker_poll_interval_seconds()
    while _STATE.running:
        _STATE.last_tick_at = _now_iso()
        try:
            _dispatch_pending_runs()
        except Exception as e:  # noqa: BLE001
            _STATE.last_error = str(e)
        time.sleep(poll)


def _task_priority(task: Task | None) -> int:
    if not task:
        return _PRIORITY_ORDER["normal"]
    return _PRIORITY_ORDER.get(task.queue_priority, _PRIORITY_ORDER["normal"])


def _running_agent_ids() -> set[str]:
    if not get_worker_per_agent_serialization_enabled():
        return set()
    tasks_by_id = {task.task_id: task for task in tasks_repo.list()}
    active_agents: set[str] = set()
    for run in runs_repo.list():
        if run.status != "running" or not run.agent_id:
            continue
        task = tasks_by_id.get(run.task_id)
        if task and task.status.value in {"running", "waiting_approval"}:
            active_agents.add(run.agent_id)
    for run_id in _ACTIVE_RUNS:
        run = runs_repo.get(run_id)
        if run and run.agent_id:
            active_agents.add(run.agent_id)
    return active_agents


def _dispatchable_pending_runs() -> list[Run]:
    pending = [run for run in runs_repo.list() if run.status == "pending"]
    if not pending:
        return []

    max_slots = max(get_worker_max_concurrent_runs(), 1)
    available_slots = max_slots - len(_ACTIVE_RUNS)
    if available_slots <= 0:
        return []

    tasks_by_id = {task.task_id: task for task in tasks_repo.list()}
    running_agents = _running_agent_ids()
    selected: list[Run] = []
    selected_agents: set[str] = set()

    pending.sort(
        key=lambda run: (
            -_task_priority(tasks_by_id.get(run.task_id)),
            run.queued_at or run.started_at or "",
        )
    )

    for run in pending:
        if run.run_id in _ACTIVE_RUNS:
            continue
        task = tasks_by_id.get(run.task_id)
        agent_id = run.agent_id or (task.assigned_agent_id if task else None)
        if get_worker_per_agent_serialization_enabled() and agent_id:
            if agent_id in running_agents or agent_id in selected_agents:
                continue
        selected.append(run)
        if agent_id:
            selected_agents.add(agent_id)
        if len(selected) >= available_slots:
            break
    return selected


def _dispatch_pending_runs() -> None:
    dispatchable = _dispatchable_pending_runs()
    for run in dispatchable:
        _start_run_execution(run.run_id)


def _try_claim_run(run: Run, task: Task, agent) -> Run | None:
    """CAS: only one worker may transition pending -> running."""
    claim_token = new_id("claim")
    claimed_at = _now_iso()
    candidate = run.model_copy(
        update={
            "status": "running",
            "started_at": claimed_at,
            "claimed_at": claimed_at,
            "claim_token": claim_token,
            "error": None,
            "environment_summary": build_environment_summary(task, agent),
        }
    )
    if runs_repo.compare_and_swap(candidate, {"status": "pending"}):
        return candidate
    return None


def _start_run_execution(run_id: str) -> None:
    with _LOCK:
        if run_id in _ACTIVE_RUNS:
            return
        _ACTIVE_RUNS.add(run_id)
    thread = threading.Thread(target=_execute_run, args=(run_id,), name=f"octopus-run-{run_id}", daemon=True)
    thread.start()


def _release_run(run_id: str) -> None:
    with _LOCK:
        _ACTIVE_RUNS.discard(run_id)


def _execute_run(run_id: str) -> None:
    try:
        run = runs_repo.get(run_id)
        if not run or run.status != "pending":
            return

        _STATE.last_run_id = run.run_id
        task = tasks_repo.get(run.task_id)
        if not task:
            runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "task_not_found"}))
            return
        task = ensure_task_correlation(task)
        agent_id = run.agent_id or task.assigned_agent_id
        if not agent_id:
            runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "task_not_assigned"}))
            return
        agent = agents_repo.get(agent_id)
        if not agent:
            runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "agent_not_found"}))
            return
        if not getattr(agent, "enabled", True):
            runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "agent_disabled"}))
            _append_event(task.task_id, "task_failed", "Task failed: assigned agent is disabled", {"run_id": run.run_id})
            tasks_repo.upsert(task.model_copy(update={"status": TaskStatus.failed, "last_error": "agent_disabled", "updated_at": _now_iso()}))
            return

        try:
            if run.queued_at:
                queued_at = datetime.fromisoformat(run.queued_at.replace("Z", "+00:00"))
                if datetime.now(tz=timezone.utc) - queued_at > timedelta(minutes=10):
                    runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "queue_timeout"}))
                    _append_event(task.task_id, "task_failed", "Task failed: queue timeout", {"run_id": run.run_id})
                    failed_task = task.model_copy(update={"status": TaskStatus.failed, "last_error": "queue_timeout", "updated_at": _now_iso()})
                    tasks_repo.upsert(failed_task)
                    append_watchdog_issue(
                        "task_worker_stalled",
                        f"Queued run {run.run_id} exceeded the worker queue timeout",
                        severity="warn",
                        task=failed_task,
                        agent_id=agent_id,
                        run_id=run.run_id,
                        raw_error="queue_timeout",
                        suggested_action="retry_run",
                        recovery_hint="The worker queue timed out before execution started.",
                        parent_run_id=run.parent_run_id,
                    )
                    return
        except Exception:
            pass

        run_claimed = _try_claim_run(run, task, agent)
        if not run_claimed:
            return

        run2 = run_claimed
        tasks_repo.upsert(task.model_copy(update={"status": TaskStatus.running, "updated_at": _now_iso()}))
        _append_event(
            task.task_id,
            TaskEvent.run_started.value,
            "Run started (worker)",
            {
                "run_id": run2.run_id,
                "agent_id": agent.agent_id,
                "parent_run_id": run2.parent_run_id,
                "queue_priority": task.queue_priority,
                "claim_token": run2.claim_token,
            },
        )
        _append_run_log(
            run2.run_id,
            2,
            "info",
            "Run started (worker)",
            {"agent_id": agent.agent_id, "queue_priority": task.queue_priority, "claim_token": run2.claim_token},
        )
        agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.running, "last_heartbeat_at": _now_iso()}))

        adapter = agent.adapter_id or ("builtin_octopus" if agent.type == "builtin" else "unknown")
        res = execute_builtin_octopus(task, run2, agent) if agent.type == "builtin" or adapter == "builtin_octopus" else execute_via_local_bridge(task, run2, agent)
        _append_run_log(run2.run_id, 3, "info", f"integration_path={res.integration_path}", res.meta)

        latest_run = runs_repo.get(run2.run_id) or run2
        latest_task = tasks_repo.get(task.task_id) or task
        # External callbacks can complete the run while the worker is still
        # unwinding the handoff path. If final state is already persisted,
        # keep that authoritative result instead of writing stale handoff data.
        if latest_run.status in {"succeeded", "failed"} or latest_task.status in {TaskStatus.succeeded, TaskStatus.failed}:
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
            return

        if res.ok and res.pending_handoff:
            runs_repo.upsert(
                latest_run.model_copy(
                    update={
                        "status": "running",
                        "finished_at": None,
                        "integration_path": res.integration_path,
                        "output_excerpt": (res.output or "")[:4000],
                        "error": None,
                        "environment_summary": build_environment_summary(task, agent, integration_path=res.integration_path),
                        "output_snapshot": {
                            "status": "pending_handoff",
                            "output": (res.output or "")[:4000],
                        },
                    }
                )
            )
            tasks_repo.upsert(
                latest_task.model_copy(
                    update={
                        "status": TaskStatus.waiting_approval,
                        "result_summary": (res.output or "")[:2000],
                        "result_payload": {"integration_path": res.integration_path, "pending_handoff": True, "meta": res.meta},
                        "updated_at": _now_iso(),
                    }
                )
            )
            _append_event(
                task.task_id,
                "external_handoff",
                "Waiting for external completion (handoff)",
                {"run_id": run2.run_id, "integration_path": res.integration_path, "parent_run_id": run2.parent_run_id},
            )
            _append_run_log(run2.run_id, 4, "info", "External handoff created; waiting for completion callback", res.meta)
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
            return

        if res.ok:
            runs_repo.upsert(
                latest_run.model_copy(
                    update={
                        "status": "succeeded",
                        "finished_at": _now_iso(),
                        "integration_path": res.integration_path,
                        "output_excerpt": (res.output or "")[:4000],
                        "error": None,
                        "environment_summary": build_environment_summary(task, agent, integration_path=res.integration_path),
                        "output_snapshot": {
                            "status": "succeeded",
                            "output": (res.output or "")[:4000],
                        },
                    }
                )
            )
            tasks_repo.upsert(
                latest_task.model_copy(
                    update={
                        "status": TaskStatus.succeeded,
                        "last_error": None,
                        "result_summary": (res.output or "")[:2000],
                        "result_payload": {"integration_path": res.integration_path, "meta": res.meta},
                        "needs_attention": False,
                        "attention_reason": None,
                        "updated_at": _now_iso(),
                    }
                )
            )
            _append_event(task.task_id, TaskEvent.task_succeeded.value, "Task succeeded (worker)", {"run_id": run2.run_id, "parent_run_id": run2.parent_run_id})
            _append_run_log(run2.run_id, 4, "info", "Execution succeeded (worker)", {"output_len": len(res.output or "")})
            agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
            return

        runs_repo.upsert(
            latest_run.model_copy(
                update={
                    "status": "failed",
                    "finished_at": _now_iso(),
                    "integration_path": res.integration_path,
                    "output_excerpt": (res.output or "")[:4000],
                    "error": res.error,
                    "environment_summary": build_environment_summary(task, agent, integration_path=res.integration_path),
                    "output_snapshot": {
                        "status": "failed",
                        "output": (res.output or "")[:4000],
                        "error": res.error,
                    },
                }
            )
        )
        tasks_repo.upsert(
            latest_task.model_copy(
                update={
                    "status": TaskStatus.failed,
                    "last_error": res.error,
                    "result_payload": {"integration_path": res.integration_path, "error": res.error, "meta": res.meta},
                    "updated_at": _now_iso(),
                }
            )
        )
        task = tasks_repo.get(task.task_id) or task
        _append_event(task.task_id, TaskEvent.task_failed.value, "Task failed (worker)", {"run_id": run2.run_id, "error": res.error, "parent_run_id": run2.parent_run_id})
        _append_run_log(run2.run_id, 4, "error", f"Execution failed (worker): {res.error}", res.meta)
        append_watchdog_issue(
            "task_failed",
            f"Worker run failed for task {task.task_id}",
            severity="error",
            task=task,
            agent_id=agent.agent_id,
            run_id=run2.run_id,
            raw_error=res.error,
            suggested_action="retry_run",
            parent_run_id=run2.parent_run_id,
        )
        if task.retry_count >= task.max_recovery_attempts:
            mark_task_attention(task, "Task failed and exhausted automatic recovery limit", source="watchdog")
        agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.degraded, "last_heartbeat_at": _now_iso()}))
    finally:
        _release_run(run_id)

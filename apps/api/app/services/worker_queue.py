from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..executor import execute_builtin_octopus, execute_via_local_bridge
from ..fsm import TaskEvent
from ..id_utils import new_id
from ..models import AgentStatus, Run, TaskStatus
from ..store.repositories import agents_repo, run_logs_repo, runs_repo, task_events_repo, tasks_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _append_event(task_id: str, typ: str, message: str | None, payload: dict[str, Any] | None = None) -> None:
    task_events_repo.upsert(
        task_events_repo.model.model_validate(
            {
                "event_id": new_id("evt"),
                "task_id": task_id,
                "type": typ,
                "message": message,
                "payload": payload,
                "created_at": _now_iso(),
            }
        )
    )


def _append_run_log(run_id: str, seq: int, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
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
            }
        )
    )


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


def get_worker_state() -> dict[str, Any]:
    return {
        "started_at": _STATE.started_at,
        "last_tick_at": _STATE.last_tick_at,
        "last_run_id": _STATE.last_run_id,
        "last_error": _STATE.last_error,
        "running": _STATE.running,
    }


def start_worker_thread() -> None:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _STATE.running = True
        _THREAD = threading.Thread(target=_loop, name="octopus-worker", daemon=True)
        _THREAD.start()


def stop_worker_thread() -> None:
    _STATE.running = False


def enqueue_run(task_id: str, agent_id: str) -> Run:
    """
    Create a pending run and let the background worker execute it.
    Persisted in runs.json; status=pending means queued.
    """
    # Ensure worker is alive even in test environments.
    start_worker_thread()
    run_id = new_id("run")
    run = Run(
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        status="pending",
        queued_at=_now_iso(),
        started_at=_now_iso(),  # kept for compatibility; worker will update when actually starts
        integration_path=None,
    )
    runs_repo.upsert(run)
    _append_event(task_id, "run_queued", "Run queued", {"run_id": run_id, "agent_id": agent_id})
    _append_run_log(run_id, 1, "info", "Run queued", {"agent_id": agent_id})
    return run


def _loop() -> None:
    poll = 0.25
    while _STATE.running:
        _STATE.last_tick_at = _now_iso()
        try:
            _process_one()
        except Exception as e:  # noqa: BLE001
            _STATE.last_error = str(e)
        time.sleep(poll)


def _process_one() -> None:
    # find the oldest pending run
    pending = [r for r in runs_repo.list() if r.status == "pending"]
    if not pending:
        return
    pending.sort(key=lambda r: (r.queued_at or r.started_at))
    run = pending[0]
    _STATE.last_run_id = run.run_id

    task = tasks_repo.get(run.task_id)
    if not task:
        runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "task_not_found"}))
        return
    agent_id = run.agent_id or task.assigned_agent_id
    if not agent_id:
        runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "task_not_assigned"}))
        return
    agent = agents_repo.get(agent_id)
    if not agent:
        runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "agent_not_found"}))
        return

    # timeout guard (beta): if run queued > 10 minutes, fail it
    try:
        if run.queued_at:
            queued_at = datetime.fromisoformat(run.queued_at.replace("Z", "+00:00"))
            if datetime.now(tz=timezone.utc) - queued_at > timedelta(minutes=10):
                runs_repo.upsert(run.model_copy(update={"status": "failed", "finished_at": _now_iso(), "error": "queue_timeout"}))
                _append_event(task.task_id, "task_failed", "Task failed: queue timeout", {"run_id": run.run_id})
                tasks_repo.upsert(task.model_copy(update={"status": TaskStatus.failed, "last_error": "queue_timeout", "updated_at": _now_iso()}))
                return
    except Exception:
        pass

    # start run
    run2 = run.model_copy(update={"status": "running", "started_at": _now_iso(), "error": None})
    runs_repo.upsert(run2)
    tasks_repo.upsert(task.model_copy(update={"status": TaskStatus.running, "updated_at": _now_iso()}))
    _append_event(task.task_id, TaskEvent.run_started.value, "Run started (worker)", {"run_id": run2.run_id, "agent_id": agent.agent_id})
    _append_run_log(run2.run_id, 2, "info", "Run started (worker)", {"agent_id": agent.agent_id})
    agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.running, "last_heartbeat_at": _now_iso()}))

    adapter = agent.adapter_id or ("builtin_octopus" if agent.type == "builtin" else "unknown")
    res = execute_builtin_octopus(task, run2, agent) if agent.type == "builtin" or adapter == "builtin_octopus" else execute_via_local_bridge(task, run2, agent)
    _append_run_log(run2.run_id, 3, "info", f"integration_path={res.integration_path}", res.meta)

    if res.ok and res.pending_handoff:
        # external handoff: keep run running, task waiting_approval; completion via callback
        runs_repo.upsert(
            run2.model_copy(
                update={
                    "status": "running",
                    "finished_at": None,
                    "integration_path": res.integration_path,
                    "output_excerpt": (res.output or "")[:4000],
                    "error": None,
                }
            )
        )
        tasks_repo.upsert(
            task.model_copy(
                update={
                    "status": TaskStatus.waiting_approval,
                    "result_summary": (res.output or "")[:2000],
                    "result_payload": {"integration_path": res.integration_path, "pending_handoff": True, "meta": res.meta},
                    "updated_at": _now_iso(),
                }
            )
        )
        _append_event(task.task_id, "external_handoff", "Waiting for external completion (handoff)", {"run_id": run2.run_id, "integration_path": res.integration_path})
        _append_run_log(run2.run_id, 4, "info", "External handoff created; waiting for completion callback", res.meta)
        agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
        return

    if res.ok:
        runs_repo.upsert(
            run2.model_copy(
                update={
                    "status": "succeeded",
                    "finished_at": _now_iso(),
                    "integration_path": res.integration_path,
                    "output_excerpt": (res.output or "")[:4000],
                    "error": None,
                }
            )
        )
        tasks_repo.upsert(
            task.model_copy(
                update={
                    "status": TaskStatus.succeeded,
                    "last_error": None,
                    "result_summary": (res.output or "")[:2000],
                    "result_payload": {"integration_path": res.integration_path, "meta": res.meta},
                    "updated_at": _now_iso(),
                }
            )
        )
        _append_event(task.task_id, TaskEvent.task_succeeded.value, "Task succeeded (worker)", {"run_id": run2.run_id})
        _append_run_log(run2.run_id, 4, "info", "Execution succeeded (worker)", {"output_len": len(res.output or "")})
        agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.idle, "last_heartbeat_at": _now_iso()}))
        return

    runs_repo.upsert(
        run2.model_copy(
            update={
                "status": "failed",
                "finished_at": _now_iso(),
                "integration_path": res.integration_path,
                "output_excerpt": (res.output or "")[:4000],
                "error": res.error,
            }
        )
    )
    tasks_repo.upsert(
        task.model_copy(
            update={
                "status": TaskStatus.failed,
                "last_error": res.error,
                "result_payload": {"integration_path": res.integration_path, "error": res.error, "meta": res.meta},
                "updated_at": _now_iso(),
            }
        )
    )
    _append_event(task.task_id, TaskEvent.task_failed.value, "Task failed (worker)", {"run_id": run2.run_id, "error": res.error})
    _append_run_log(run2.run_id, 4, "error", f"Execution failed (worker): {res.error}", res.meta)
    agents_repo.upsert(agent.model_copy(update={"status": AgentStatus.degraded, "last_heartbeat_at": _now_iso()}))


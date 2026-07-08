from __future__ import annotations

from typing import Any

from ..models import Run, Task, TaskStatus
from ..store.repositories import runs_repo, tasks_repo
from .runtime_audit import append_task_event, now_iso
from .run_steps import complete_run_timeline


_FINAL_TASK_STATUSES = {
    TaskStatus.succeeded,
    TaskStatus.failed,
    TaskStatus.cancelled,
    TaskStatus.expired,
}


def is_permission_denied_failure(*values: Any) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            if str(value.get("error_kind") or "").lower() == "permission_denied":
                return True
            if str(value.get("winerror") or "").strip() == "5":
                return True
            if is_permission_denied_failure(*value.values()):
                return True
            continue
        if isinstance(value, (list, tuple, set)):
            if is_permission_denied_failure(*value):
                return True
            continue
        text = str(value).lower()
        if "permissionerror" in text or "permission denied" in text or "access is denied" in text:
            return True
        if "winerror 5" in text or "[winerror 5]" in text:
            return True
    return False


def _snapshot_status(run: Run) -> str | None:
    snapshot = run.output_snapshot if isinstance(run.output_snapshot, dict) else None
    raw = snapshot.get("status") if snapshot else None
    return str(raw) if raw else None


def _merge_payload(task: Task, updates: dict[str, Any]) -> dict[str, Any]:
    payload = dict(task.result_payload or {})
    payload.update({key: value for key, value in updates.items() if value is not None})
    return payload


def reconcile_task_with_run(task: Task, run: Run | None, *, source: str) -> Task:
    """Conservatively reconcile Task.status from authoritative Run evidence.

    RunStep is intentionally not consulted here. It remains an execution
    timeline/audit signal, while task outcome follows run and integration
    results.
    """
    if not run or run.task_id != task.task_id:
        return task

    status = _snapshot_status(run)
    ts = now_iso()

    if status == "pending_handoff" and run.status == "running":
        if task.status in _FINAL_TASK_STATUSES or task.status == TaskStatus.waiting_approval:
            return task
        updated = task.model_copy(
            update={
                "status": TaskStatus.waiting_approval,
                "result_summary": run.output_excerpt or task.result_summary,
                "result_payload": _merge_payload(
                    task,
                    {
                        "integration_path": run.integration_path,
                        "pending_handoff": True,
                    },
                ),
                "updated_at": ts,
            }
        )
        tasks_repo.upsert(updated)
        append_task_event(
            task.task_id,
            "task_status_reconciled",
            "Task status reconciled from pending handoff run",
            correlation_id=task.correlation_id,
            payload={"run_id": run.run_id, "source": source, "status": updated.status.value},
        )
        return updated

    if run.status == "succeeded":
        if task.status in _FINAL_TASK_STATUSES:
            return task
        updated = task.model_copy(
            update={
                "status": TaskStatus.succeeded,
                "last_error": None,
                "result_summary": run.output_excerpt or task.result_summary,
                "result_payload": _merge_payload(
                    task,
                    {
                        "integration_path": run.integration_path,
                        "output": run.output_excerpt,
                    },
                ),
                "needs_attention": False,
                "attention_reason": None,
                "updated_at": ts,
            }
        )
        tasks_repo.upsert(updated)
        append_task_event(
            task.task_id,
            "task_status_reconciled",
            "Task status reconciled from succeeded run",
            correlation_id=task.correlation_id,
            payload={"run_id": run.run_id, "source": source, "status": updated.status.value},
        )
        return updated

    if run.status == "failed":
        if task.status in {TaskStatus.failed, TaskStatus.cancelled, TaskStatus.expired}:
            return task
        permission_denied = is_permission_denied_failure(run.error, run.output_snapshot, task.result_payload)
        attention_reason = (
            "Permission denied by local execution environment; manual review is required."
            if permission_denied
            else task.attention_reason
        )
        updated = task.model_copy(
            update={
                "status": TaskStatus.failed,
                "last_error": run.error or task.last_error,
                "result_payload": _merge_payload(
                    task,
                    {
                        "integration_path": run.integration_path,
                        "error": run.error,
                    },
                ),
                "needs_attention": task.needs_attention or permission_denied,
                "attention_reason": attention_reason,
                "updated_at": ts,
            }
        )
        tasks_repo.upsert(updated)
        append_task_event(
            task.task_id,
            "task_status_reconciled",
            "Task status reconciled from failed run",
            correlation_id=task.correlation_id,
            payload={
                "run_id": run.run_id,
                "source": source,
                "status": updated.status.value,
                "permission_denied": permission_denied,
            },
        )
        return updated

    return task


def _run_sort_key(run: Run) -> str:
    return run.finished_at or run.started_at or run.queued_at or ""


def _latest_run_for_task(task: Task, runs_by_task: dict[str, list[Run]]) -> Run | None:
    runs = runs_by_task.get(task.task_id) or []
    if not runs:
        return None
    if task.last_run_id:
        explicit = next((run for run in runs if run.run_id == task.last_run_id), None)
        if explicit:
            return explicit
    runs.sort(key=_run_sort_key, reverse=True)
    return runs[0]


def reconcile_all_tasks_with_latest_runs(*, source: str) -> dict[str, int]:
    """Bring legacy persisted task state back in line with terminal runs.

    This is a conservative startup/ops reconciliation pass. Run remains the
    authority for task outcome; RunStep is only finalized to match an already
    terminal run so the execution audit does not show stale running/pending
    steps for historical attempts.
    """
    runs_by_task: dict[str, list[Run]] = {}
    for run in runs_repo.list():
        runs_by_task.setdefault(run.task_id, []).append(run)

    scanned = 0
    reconciled = 0
    timelines_completed = 0
    for task in tasks_repo.list():
        scanned += 1
        run = _latest_run_for_task(task, runs_by_task)
        if not run or run.status not in {"succeeded", "failed"}:
            continue

        before = task.status
        updated = reconcile_task_with_run(task, run, source=source)
        if updated.status != before:
            reconciled += 1

        complete_run_timeline(run.run_id, succeeded=run.status == "succeeded")
        timelines_completed += 1

    return {
        "tasks_scanned": scanned,
        "tasks_reconciled": reconciled,
        "timelines_completed": timelines_completed,
    }

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..models import TaskStatus, WatchdogEvent
from ..settings_env import get_callback_wait_minutes, get_default_max_recovery_attempts, get_local_bridge_url, get_stalled_task_minutes
from ..store.repositories import agents_repo, runs_repo, tasks_repo, watchdog_events_repo
from .advisor import upsert_advisor_suggestion
from .runtime_audit import (
    append_task_event,
    append_watchdog_issue,
    claim_processed_receipt,
    ensure_task_correlation,
    finalize_processed_receipt,
    mark_task_attention,
    now_iso,
    normalize_issue,
)
from .task_status_reconciliation import is_permission_denied_failure
from .task_lifecycle import retry_task


_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()
_RUNNING = False


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _latest_issue_state() -> dict[tuple[str | None, str, str], WatchdogEvent]:
    latest: dict[tuple[str | None, str, str], WatchdogEvent] = {}
    for event in watchdog_events_repo.list():
        if not event.issue_class or not event.normalized_issue_signature:
            continue
        key = (event.task_id, event.issue_class, event.normalized_issue_signature)
        existing = latest.get(key)
        if existing is None or existing.created_at < event.created_at:
            latest[key] = event
    return latest


def stop_runtime_supervision_thread() -> None:
    global _RUNNING
    _RUNNING = False


def _record_issue_occurrence(
    issue_type: str,
    message: str,
    *,
    severity: str,
    task=None,
    agent_id: str | None = None,
    run_id: str | None = None,
    raw_error: str | None = None,
    suggested_action: str | None = None,
    recovery_hint: str | None = None,
    latest_state: dict[tuple[str | None, str, str], WatchdogEvent],
) -> tuple[WatchdogEvent, bool]:
    issue_class, signature = normalize_issue(raw_error or message, issue_type)
    key = (task.task_id if task else None, issue_class, signature)
    existing = latest_state.get(key)
    if existing and existing.issue_status in ("open", "processing"):
        updated = append_watchdog_issue(
            issue_type,
            message,
            severity=severity,
            task=task,
            agent_id=agent_id,
            run_id=run_id,
            raw_error=raw_error,
            suggested_action=suggested_action,
            source="watchdog",
            issue_status=existing.issue_status or "open",
            recovery_hint=recovery_hint,
            event_id=existing.event_id,
            created_at=existing.created_at,
            first_seen_at=existing.first_seen_at or existing.created_at,
            last_seen_at=now_iso(),
            occurrence_count=max(existing.occurrence_count, 1) + 1,
        )
        latest_state[key] = updated
        return updated, False
    if existing and existing.issue_status == "escalated":
        escalate_event_id = existing.event_id if existing.source == "watchdog" else None
        escalate_created_at = existing.created_at if existing.source == "watchdog" else None
        escalate_first_seen_at = (
            existing.first_seen_at or existing.created_at if existing.source == "watchdog" else None
        )
        escalate_occurrence_count = max(existing.occurrence_count, 1) + 1 if existing.source == "watchdog" else 1
        updated = append_watchdog_issue(
            issue_type,
            message,
            severity=severity,
            task=task,
            agent_id=agent_id,
            run_id=run_id,
            raw_error=raw_error,
            suggested_action="defer_to_human",
            source="watchdog",
            issue_status="escalated",
            recovery_hint=recovery_hint,
            parent_run_id=existing.parent_run_id,
            event_id=escalate_event_id,
            created_at=escalate_created_at,
            first_seen_at=escalate_first_seen_at,
            last_seen_at=now_iso(),
            occurrence_count=escalate_occurrence_count,
        )
        latest_state[key] = updated
        return updated, False

    event = append_watchdog_issue(
        issue_type,
        message,
        severity=severity,
        task=task,
        agent_id=agent_id,
        run_id=run_id,
        raw_error=raw_error,
        suggested_action=suggested_action,
        source="watchdog",
        issue_status="open",
        recovery_hint=recovery_hint,
    )
    latest_state[key] = event
    return event, True


def scan_watchdog_issues() -> list[WatchdogEvent]:
    occurrences: list[WatchdogEvent] = []
    now = datetime.now(tz=timezone.utc)
    stalled_after = timedelta(minutes=get_stalled_task_minutes())
    callback_after = timedelta(minutes=get_callback_wait_minutes())
    latest_state = _latest_issue_state()

    for task in tasks_repo.list():
        task = ensure_task_correlation(task)
        updated_at = _parse_iso(task.updated_at or task.created_at)
        if task.status == TaskStatus.running and updated_at and updated_at < now - stalled_after:
            event, _is_new = _record_issue_occurrence(
                "task_worker_stalled",
                f"Task {task.task_id} is running without progress",
                severity="warn",
                task=task,
                run_id=task.last_run_id,
                raw_error="queue_timeout",
                suggested_action="retry_run",
                recovery_hint="Fixer may retry once; otherwise task will require human attention.",
                latest_state=latest_state,
            )
            occurrences.append(event)

        if task.status == TaskStatus.waiting_approval and updated_at and updated_at < now - callback_after:
            run_id = task.last_run_id
            event, _is_new = _record_issue_occurrence(
                "external_callback_missing",
                f"Task {task.task_id} is waiting too long for external callback",
                severity="warn",
                task=task,
                run_id=run_id,
                raw_error="external_callback_missing",
                suggested_action="mark_needs_attention",
                recovery_hint="Fixer will not auto-complete this task; operator review is required.",
                latest_state=latest_state,
            )
            occurrences.append(event)

    try:
        reachable = False
        with httpx.Client(timeout=3.0) as client:
            reachable = client.get(f"{get_local_bridge_url()}/health").status_code == 200
    except Exception:
        reachable = False
    if not reachable:
        event, _is_new = _record_issue_occurrence(
            "bridge_unreachable",
            "Local Bridge health check failed",
            severity="error",
            raw_error="local_bridge_unreachable",
            suggested_action="probe_bridge",
            recovery_hint="Fixer will probe the bridge, then defer to human if it remains offline.",
            latest_state=latest_state,
        )
        occurrences.append(event)

    return occurrences


def run_fixer_once() -> list[WatchdogEvent]:
    emitted: list[WatchdogEvent] = []
    latest_state = _latest_issue_state()
    for _key, issue in latest_state.items():
        if issue.issue_status not in ("open", "processing"):
            continue
        receipt_key = f"{issue.event_id}:{issue.issue_class}:{issue.normalized_issue_signature}"
        claimed, existing_receipt = claim_processed_receipt(
            "fixer_action",
            receipt_key,
            task_id=issue.task_id,
            run_id=issue.related_run_id,
            correlation_id=issue.correlation_id,
            payload={"issue_event_id": issue.event_id, "issue_class": issue.issue_class},
        )
        if not claimed:
            continue

        task = tasks_repo.get(issue.task_id) if issue.task_id else None
        if task:
            task = ensure_task_correlation(task)

        try:
            if issue.issue_class in ("task_worker_stalled", "task_failed") and task:
                if task.recovery_attempt_count >= task.max_recovery_attempts:
                    task = mark_task_attention(task, "Task stalled and exceeded automatic recovery limit", source="fixer")
                    event = append_watchdog_issue(
                        "defer_to_human",
                        f"Task {task.task_id} exceeded automatic recovery limit",
                        severity="warn",
                        task=task,
                        raw_error=issue.raw_error,
                        source="fixer",
                        issue_status="escalated",
                        suggested_action="defer_to_human",
                        recovery_hint="Open the task detail page and decide whether to retry manually.",
                    )
                    append_task_event(
                        task.task_id,
                        "escalation_opened",
                        "Task stalled and was escalated to human review",
                        correlation_id=task.correlation_id,
                        payload={"issue_class": issue.issue_class, "parent_run_id": issue.related_run_id},
                    )
                    upsert_advisor_suggestion(
                        suggestion_type="recovery_suggestion",
                        target_type="task",
                        target_id=task.task_id,
                        issue_class="task_worker_stalled",
                        title="Defer stalled task to human review",
                        summary="This task exhausted its automatic stalled-task recovery budget.",
                        rationale=(
                            f"Task {task.task_id} has recovery_attempt_count={task.recovery_attempt_count} "
                            f"with max_recovery_attempts={task.max_recovery_attempts}."
                        ),
                        recommended_action="Review the escalation, inspect the timeline, and resolve or rerun manually.",
                        evidence_refs=[
                            {"kind": "task", "id": task.task_id},
                            {"kind": "watchdog_event", "id": event.event_id},
                            {"kind": "run", "id": issue.related_run_id},
                        ],
                        severity="critical",
                        requires_confirmation=True,
                        correlation_id=task.correlation_id,
                        source_task_id=task.task_id,
                        source_run_id=issue.related_run_id,
                        source_watchdog_event_id=event.event_id,
                    )
                    finalize_processed_receipt(
                        "fixer_action",
                        receipt_key,
                        status="completed",
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        result_ref=event.event_id,
                    )
                    emitted.append(event)
                    continue

                task = task.model_copy(
                    update={
                        "status": TaskStatus.failed,
                        "last_error": issue.raw_error or "task_worker_stalled",
                        "updated_at": now_iso(),
                        "recovery_attempt_count": task.recovery_attempt_count + 1,
                    }
                )
                tasks_repo.upsert(task)
                append_task_event(
                    task.task_id,
                    "fixer_mark_failed",
                    "Fixer marked stalled task failed",
                    correlation_id=task.correlation_id,
                    payload={"issue_class": issue.issue_class},
                )
                if (issue.raw_error or "").lower() == "queue_timeout":
                    task = mark_task_attention(
                        task,
                        "Queued run timed out; manual review is required before retry.",
                        source="fixer",
                    )
                    event = append_watchdog_issue(
                        "fixer_defer_queue_timeout",
                        f"Task {task.task_id} timed out in queue and was not automatically retried",
                        severity="warn",
                        task=task,
                        raw_error=issue.raw_error,
                        source="fixer",
                        issue_status="escalated",
                        suggested_action="defer_to_human",
                        recovery_hint="Confirm the assigned agent is available, then retry manually.",
                        parent_run_id=issue.related_run_id,
                    )
                    finalize_processed_receipt(
                        "fixer_action",
                        receipt_key,
                        status="completed",
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        result_ref=event.event_id,
                    )
                    emitted.append(event)
                    continue
                if is_permission_denied_failure(issue.raw_error, task.last_error, task.result_payload):
                    task = mark_task_attention(
                        task,
                        "Permission denied by local execution environment; manual review is required before retry.",
                        source="fixer",
                    )
                    event = append_watchdog_issue(
                        "fixer_defer_permission_denied",
                        f"Task {task.task_id} failed with a permission error and was not automatically retried",
                        severity="warn",
                        task=task,
                        raw_error=issue.raw_error,
                        source="fixer",
                        issue_status="escalated",
                        suggested_action="defer_to_human",
                        recovery_hint="Review local CLI permissions before retrying this task.",
                        parent_run_id=issue.related_run_id,
                    )
                    finalize_processed_receipt(
                        "fixer_action",
                        receipt_key,
                        status="completed",
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        result_ref=event.event_id,
                    )
                    emitted.append(event)
                    continue
                retried = retry_task(task.task_id)
                event = append_watchdog_issue(
                    "fixer_retry",
                    f"Fixer retried {'failed' if issue.issue_class == 'task_failed' else 'stalled'} task {task.task_id}",
                    severity="info",
                    task=retried,
                    raw_error=issue.raw_error,
                    source="fixer",
                    issue_status="resolved",
                    suggested_action="retry_run",
                    recovery_hint="Task was returned to assigned state for another run.",
                    parent_run_id=issue.related_run_id,
                )
                finalize_processed_receipt(
                    "fixer_action",
                    receipt_key,
                    status="completed",
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    result_ref=event.event_id,
                )
                emitted.append(event)
                continue

            if issue.issue_class == "bridge_timeout":
                bridge_ok = False
                try:
                    with httpx.Client(timeout=3.0) as client:
                        bridge_ok = client.get(f"{get_local_bridge_url()}/health").status_code == 200
                except Exception:
                    bridge_ok = False
                event = append_watchdog_issue(
                    "fixer_bridge_probe",
                    "Fixer probed Local Bridge",
                    severity="info" if bridge_ok else "warn",
                    raw_error=issue.raw_error,
                    source="fixer",
                    issue_status="resolved" if bridge_ok else "escalated",
                    suggested_action="probe_bridge" if bridge_ok else "defer_to_human",
                    recovery_hint="Bridge responded successfully." if bridge_ok else "Bridge still unreachable; operator action is required.",
                )
                finalize_processed_receipt(
                    "fixer_action",
                    receipt_key,
                    status="completed",
                    result_ref=event.event_id,
                    payload={"bridge_ok": bridge_ok},
                )
                emitted.append(event)
                continue

            if issue.issue_class == "external_callback_missing" and task:
                task = mark_task_attention(task, "External callback missing; manual follow-up is required", source="fixer")
                event = append_watchdog_issue(
                    "defer_to_human",
                    f"Task {task.task_id} requires human follow-up for missing callback",
                    severity="warn",
                    task=task,
                    run_id=issue.related_run_id,
                    raw_error=issue.raw_error,
                    source="fixer",
                    issue_status="escalated",
                    suggested_action="mark_needs_attention",
                    recovery_hint="Submit the callback manually or inspect the external agent handoff.",
                )
                append_task_event(
                    task.task_id,
                    "escalation_opened",
                    "Missing external callback escalated to human review",
                    correlation_id=task.correlation_id,
                    payload={"issue_class": issue.issue_class, "parent_run_id": issue.related_run_id},
                )
                upsert_advisor_suggestion(
                    suggestion_type="recovery_suggestion",
                    target_type="task",
                    target_id=task.task_id,
                    issue_class="external_callback_missing",
                    title="Review handoff channel or take over manually",
                    summary="The external agent handoff did not return a callback within the expected window.",
                    rationale=(
                        f"Task {task.task_id} remained in waiting_approval long enough to trigger "
                        "the external callback missing watchdog rule."
                    ),
                    recommended_action="Check the handoff channel, then submit the callback manually or continue the task by hand.",
                    evidence_refs=[
                        {"kind": "task", "id": task.task_id},
                        {"kind": "watchdog_event", "id": event.event_id},
                        {"kind": "run", "id": issue.related_run_id},
                    ],
                    severity="warning",
                    requires_confirmation=True,
                    correlation_id=task.correlation_id,
                    source_task_id=task.task_id,
                    source_run_id=issue.related_run_id,
                    source_watchdog_event_id=event.event_id,
                )
                finalize_processed_receipt(
                    "fixer_action",
                    receipt_key,
                    status="completed",
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    result_ref=event.event_id,
                )
                emitted.append(event)
                continue

            finalize_processed_receipt(
                "fixer_action",
                receipt_key,
                status="failed",
                task_id=issue.task_id,
                run_id=issue.related_run_id,
                correlation_id=issue.correlation_id,
                payload={"reason": "no_matching_fixer_path"},
            )
        except Exception as exc:
            finalize_processed_receipt(
                "fixer_action",
                receipt_key,
                status="failed",
                task_id=issue.task_id,
                run_id=issue.related_run_id,
                correlation_id=issue.correlation_id,
                payload={"reason": "fixer_exception", "error": str(exc)},
            )
            raise

    return emitted


def run_runtime_supervision_cycle() -> dict[str, int]:
    issues = scan_watchdog_issues()
    fixes = run_fixer_once()
    return {"issues_detected": len(issues), "fixes_emitted": len(fixes)}


def _loop() -> None:
    global _RUNNING
    while _RUNNING:
        try:
            run_runtime_supervision_cycle()
        except Exception:
            pass
        time.sleep(2.0)


def start_runtime_supervision_thread() -> None:
    global _THREAD, _RUNNING
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _RUNNING = True
        _THREAD = threading.Thread(target=_loop, name="octopus-runtime-supervision", daemon=True)
        _THREAD.start()

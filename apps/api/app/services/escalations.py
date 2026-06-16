from __future__ import annotations

from typing import Literal

from fastapi import HTTPException

from ..models import EscalationActionBody, TaskStatus, WatchdogEvent
from ..store.repositories import tasks_repo, watchdog_events_repo
from .runtime_audit import append_task_event, append_watchdog_issue, now_iso


def _latest_issue_state() -> list[WatchdogEvent]:
    latest: dict[tuple[str | None, str | None, str | None], WatchdogEvent] = {}
    for event in watchdog_events_repo.list():
        key = (event.task_id, event.issue_class, event.normalized_issue_signature)
        existing = latest.get(key)
        if existing is None or (existing.last_seen_at or existing.created_at) < (event.last_seen_at or event.created_at):
            latest[key] = event
    return sorted(
        latest.values(),
        key=lambda item: item.last_seen_at or item.created_at,
        reverse=True,
    )


def list_escalations(status: str | None = None) -> list[WatchdogEvent]:
    items = _latest_issue_state()
    if status:
        items = [item for item in items if item.issue_status == status]
    return items


def _clear_task_attention(task_id: str, *, correlation_id: str | None, reason: str) -> None:
    task = tasks_repo.get(task_id)
    if not task or not task.needs_attention:
        return
    tasks_repo.upsert(
        task.model_copy(
            update={
                "needs_attention": False,
                "attention_reason": None,
                "updated_at": now_iso(),
            }
        )
    )
    append_task_event(
        task_id,
        "task_attention_cleared",
        reason,
        correlation_id=correlation_id,
        payload={"reason": reason, "source": "human"},
    )


def update_escalation(
    event_id: str,
    action: Literal["processing", "resolved"],
    body: EscalationActionBody | None = None,
) -> WatchdogEvent:
    existing = watchdog_events_repo.get(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="escalation_not_found")

    task = tasks_repo.get(existing.task_id) if existing.task_id else None
    note = (body.note.strip() if body and body.note else None) or (
        "Operator acknowledged escalation."
        if action == "processing"
        else "Operator resolved escalation."
    )
    human_event = append_watchdog_issue(
        existing.issue_class or existing.type,
        note,
        severity=existing.severity,
        task=task,
        agent_id=existing.agent_id,
        run_id=existing.related_run_id,
        raw_error=existing.raw_error or existing.normalized_issue_signature or existing.issue_class,
        suggested_action=existing.suggested_action,
        source="human",
        issue_status=action,
        recovery_hint=existing.recovery_hint,
        parent_run_id=existing.parent_run_id,
    )

    if existing.task_id:
        append_task_event(
            existing.task_id,
            "escalation_acknowledged" if action == "processing" else "escalation_resolved",
            note,
            correlation_id=existing.correlation_id,
            payload={
                "issue_class": existing.issue_class,
                "watchdog_event_id": existing.event_id,
                "resolution_event_id": human_event.event_id,
            },
        )

    if action == "resolved" and existing.task_id:
        _clear_task_attention(existing.task_id, correlation_id=existing.correlation_id, reason=note)

    return human_event

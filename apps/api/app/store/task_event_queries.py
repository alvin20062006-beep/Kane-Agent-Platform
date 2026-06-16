"""Filtered task-event reads (Phase 5)."""

from __future__ import annotations

from ..models import TaskEventRecord
from .repositories import task_events_repo


def list_events_for_task(task_id: str, *, tail: int | None = None) -> tuple[list[TaskEventRecord], int]:
    events = [event for event in task_events_repo.list() if event.task_id == task_id]
    events.sort(key=lambda x: x.created_at)
    total = len(events)
    if tail and total > tail:
        events = events[-tail:]
    return events, total

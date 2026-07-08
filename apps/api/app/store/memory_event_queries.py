"""Filtered reads for Kane Memory Ledger."""

from __future__ import annotations

from ..models import MemoryEvent
from .repositories import memory_events_repo


def list_memory_events(
    *,
    memory_id: str | None = None,
    event_type: str | None = None,
    subject_key: str | None = None,
) -> list[MemoryEvent]:
    events = memory_events_repo.list()
    if memory_id:
        events = [event for event in events if event.memory_id == memory_id]
    if event_type:
        events = [event for event in events if event.event_type == event_type]
    if subject_key:
        events = [event for event in events if event.subject_key == subject_key]
    events.sort(key=lambda event: event.created_at, reverse=True)
    return events

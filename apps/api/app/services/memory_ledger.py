from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import ActiveMemorySnapshot, MemoryEvent, MemoryIndexEntry, MemoryItem
from ..store.repositories import (
    active_memory_snapshots_repo,
    memory_events_repo,
    memory_index_repo,
    memory_repo,
)
from .runtime_audit import now_iso

ACTIVE_SNAPSHOT_ID = "active_default"


def _subject_key_for_item(item: MemoryItem) -> str:
    if item.scope_type and item.scope_id:
        return f"{item.scope_type}:{item.scope_id}:{item.memory_type}:{item.memory_id}"
    return f"memory:{item.memory_id}"


def _index_id(memory_id: str) -> str:
    return f"memory:{memory_id}"


def _status_from_item(item: MemoryItem) -> str:
    if item.status == "approved":
        return "active"
    if item.status == "rejected":
        return "rejected"
    return "candidate"


def _content_json_for_item(item: MemoryItem) -> dict[str, Any]:
    return {
        "memory_type": item.memory_type,
        "title": item.title,
        "body": item.content,
        "tags": list(item.tags),
    }


def _value_json_for_item(item: MemoryItem) -> dict[str, Any]:
    return {
        "status": item.status,
        "confidence": item.confidence,
    }


def rebuild_active_snapshot() -> ActiveMemorySnapshot:
    active_entries = [entry for entry in memory_index_repo.list() if entry.status == "active"]
    active_entries.sort(key=lambda entry: entry.updated_at, reverse=True)
    snapshot = ActiveMemorySnapshot(
        snapshot_id=ACTIVE_SNAPSHOT_ID,
        memory_ids=[entry.memory_id for entry in active_entries],
        event_ids=[entry.latest_event_id for entry in active_entries if entry.latest_event_id],
        value_json={
            "items": [
                {
                    "memory_id": entry.memory_id,
                    "subject_key": entry.subject_key,
                    "memory_type": entry.memory_type,
                    "title": entry.title,
                    "scope_type": entry.scope_type,
                    "scope_id": entry.scope_id,
                    "tags": entry.tags,
                    "latest_event_id": entry.latest_event_id,
                }
                for entry in active_entries
            ],
            "prompt_policy": "Do not inject the ledger directly; use Active Snapshot plus Relevant Evidence.",
        },
        updated_at=now_iso(),
    )
    return active_memory_snapshots_repo.upsert(snapshot)


def _apply_event_to_index(event: MemoryEvent) -> None:
    if not event.memory_id:
        rebuild_active_snapshot()
        return
    existing = memory_index_repo.get(_index_id(event.memory_id))
    memory = memory_repo.get(event.memory_id)
    status = existing.status if existing else "candidate"
    if memory:
        status = _status_from_item(memory)
    if event.event_type in {"superseded"}:
        status = "superseded"
    elif event.event_type in {"invalidated"}:
        status = "invalidated"
    elif event.event_type in {"user_deleted"}:
        status = "deleted"
    elif event.event_type in {"user_purged"}:
        status = "purged"
    elif event.event_type in {"user_approved", "task_result_recorded"}:
        status = "active"
    elif event.event_type in {"user_rejected"}:
        status = "rejected"
    title = str(event.content_json.get("title") or (memory.title if memory else event.memory_id))
    memory_type = str(event.content_json.get("memory_type") or (memory.memory_type if memory else "event"))
    tags_raw = event.content_json.get("tags")
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else list(memory.tags) if memory else []
    entry = MemoryIndexEntry(
        index_id=_index_id(event.memory_id),
        memory_id=event.memory_id,
        subject_key=event.subject_key,
        status=status,  # type: ignore[arg-type]
        memory_type=memory_type,
        title=title,
        scope_type=event.scope_type,
        scope_id=event.scope_id,
        source_type=event.source_type,
        source_id=event.source_id,
        latest_event_id=event.event_id,
        tags=tags,
        updated_at=now_iso(),
        value_json=event.value_json,
    )
    memory_index_repo.upsert(entry)
    rebuild_active_snapshot()


def append_memory_event(
    *,
    event_type: str,
    memory_id: str | None = None,
    subject_key: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    run_id: str | None = None,
    run_step_id: str | None = None,
    task_id: str | None = None,
    conversation_id: str | None = None,
    skill_id: str | None = None,
    decision_id: str | None = None,
    failure_id: str | None = None,
    content_json: dict[str, Any] | None = None,
    value_json: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    confidence: float | None = None,
    policy_result: dict[str, Any] | None = None,
    supersedes_event_id: str | None = None,
    invalidates_event_id: str | None = None,
    created_by: str = "ai",
    metadata: dict[str, Any] | None = None,
) -> MemoryEvent:
    event = MemoryEvent(
        event_id=new_id("mevt"),
        memory_id=memory_id,
        event_type=event_type,  # type: ignore[arg-type]
        subject_key=subject_key,
        scope_type=scope_type,
        scope_id=scope_id,
        source_type=source_type,
        source_id=source_id,
        run_id=run_id,
        run_step_id=run_step_id,
        task_id=task_id,
        conversation_id=conversation_id,
        skill_id=skill_id,
        decision_id=decision_id,
        failure_id=failure_id,
        content_json=content_json or {},
        value_json=value_json or {},
        evidence_refs=evidence_refs or [],
        confidence=confidence,
        policy_result=policy_result,
        supersedes_event_id=supersedes_event_id,
        invalidates_event_id=invalidates_event_id,
        created_by=created_by,  # type: ignore[arg-type]
        created_at=now_iso(),
        metadata=metadata or {},
    )
    memory_events_repo.upsert(event)
    _apply_event_to_index(event)
    return event


def record_memory_item_event(
    item: MemoryItem,
    *,
    event_type: str,
    created_by: str = "ai",
    metadata: dict[str, Any] | None = None,
) -> MemoryEvent:
    return append_memory_event(
        event_type=event_type,
        memory_id=item.memory_id,
        subject_key=_subject_key_for_item(item),
        scope_type=item.scope_type,
        scope_id=item.scope_id,
        source_type=item.source_type,
        source_id=item.source_id,
        task_id=item.task_id,
        conversation_id=item.conversation_id,
        content_json=_content_json_for_item(item),
        value_json=_value_json_for_item(item),
        confidence=item.confidence,
        created_by=created_by,
        metadata=metadata,
    )


def user_delete_memory(memory_id: str) -> None:
    item = memory_repo.get(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail="memory_not_found")
    record_memory_item_event(item, event_type="user_deleted", created_by="user")
    memory_repo.delete(memory_id)


def user_rewrite_memory(
    memory_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
) -> MemoryItem:
    item = memory_repo.get(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail="memory_not_found")
    updates: dict[str, Any] = {"created_at": item.created_at}
    if title is not None:
        updates["title"] = title
    if content is not None:
        updates["content"] = content
    if status is not None:
        updates["status"] = status
    if tags is not None:
        updates["tags"] = tags
    updated = memory_repo.upsert(item.model_copy(update=updates))
    record_memory_item_event(
        updated,
        event_type="user_rewritten",
        created_by="user",
        metadata={"reason": reason} if reason else None,
    )
    return updated


def user_purge_memory(
    *,
    memory_ids: list[str] | None = None,
    include_ledger: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    items = memory_repo.list()
    if memory_ids is not None:
        wanted = set(memory_ids)
        items = [item for item in items if item.memory_id in wanted]
    purged_ids = [item.memory_id for item in items]
    event = append_memory_event(
        event_type="user_purged",
        content_json={"memory_ids": purged_ids},
        value_json={"count": len(purged_ids), "include_ledger": include_ledger},
        created_by="user",
        metadata={"reason": reason} if reason else {},
    )
    for item in items:
        memory_repo.delete(item.memory_id)
        existing = memory_index_repo.get(_index_id(item.memory_id))
        if existing:
            memory_index_repo.upsert(
                existing.model_copy(
                    update={"status": "purged", "latest_event_id": event.event_id, "updated_at": now_iso()}
                )
            )
    if include_ledger:
        for ledger_event in list(memory_events_repo.list()):
            if ledger_event.memory_id in purged_ids:
                memory_events_repo.delete(ledger_event.event_id)
    rebuild_active_snapshot()
    return {"event": event, "purged_memory_ids": purged_ids}

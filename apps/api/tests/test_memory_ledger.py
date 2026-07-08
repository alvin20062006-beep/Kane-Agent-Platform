from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import MemoryItem
from app.services.memory_ledger import record_memory_item_event
from app.store.repositories import memory_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _create_memory(*, status: str = "approved", memory_type: str = "test_fact") -> MemoryItem:
    item = MemoryItem(
        memory_id=new_id("mem"),
        memory_type=memory_type,
        title=f"PR-2 ledger smoke {new_id('title')}",
        content="Structured memory ledger smoke content.",
        confidence=0.8,
        status=status,  # type: ignore[arg-type]
        source_type="test",
        source_id=new_id("src"),
        scope_type="task",
        scope_id=new_id("task"),
        tags=["pr-2", "ledger"],
        created_at=_now_iso(),
    )
    memory_repo.upsert(item)
    return item


def test_memory_event_can_be_appended_and_read():
    client = TestClient(app)
    memory_id = new_id("mem")
    subject_key = f"test:{memory_id}"

    response = client.post(
        "/memory/events",
        json={
            "event_type": "observed",
            "memory_id": memory_id,
            "subject_key": subject_key,
            "scope_type": "task",
            "scope_id": new_id("task"),
            "content_json": {"kind": "fact", "text": "append-only smoke"},
            "value_json": {"fact": "append-only smoke"},
            "created_by": "ai",
        },
    )

    assert response.status_code == 200
    event = response.json()["data"]
    assert event["memory_id"] == memory_id
    assert event["content_json"]["kind"] == "fact"
    assert event["value_json"]["fact"] == "append-only smoke"

    listed = client.get("/memory/events", params={"memory_id": memory_id})

    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(item["event_id"] == event["event_id"] for item in items)


def test_memory_index_and_active_snapshot_project_current_memory_without_replacing_legacy_api():
    client = TestClient(app)
    memory = _create_memory(status="approved")

    event = record_memory_item_event(
        memory,
        event_type="task_result_recorded",
        created_by="ai",
        metadata={"test": "pr-2"},
    )

    legacy = client.get("/memory")
    assert legacy.status_code == 200
    assert any(item["memory_id"] == memory.memory_id for item in legacy.json()["items"])

    index = client.get("/memory/index", params={"status": "active"})
    assert index.status_code == 200
    assert any(item["memory_id"] == memory.memory_id for item in index.json()["items"])

    snapshot = client.get("/memory/snapshot")
    assert snapshot.status_code == 200
    data = snapshot.json()["data"]
    assert memory.memory_id in data["memory_ids"]
    assert event.event_id in data["event_ids"]
    assert "ledger" in snapshot.json()["note"].lower()


def test_supersede_and_invalidate_events_are_recorded():
    client = TestClient(app)
    superseded = _create_memory(status="approved")
    invalidated = _create_memory(status="approved")
    superseded_event = record_memory_item_event(superseded, event_type="task_result_recorded", created_by="ai")
    invalidated_event = record_memory_item_event(invalidated, event_type="task_result_recorded", created_by="ai")

    supersede_response = client.post(
        f"/memory/{superseded.memory_id}/events/supersede",
        json={
            "supersedes_event_id": superseded_event.event_id,
            "content_json": {"reason": "newer memory exists"},
            "created_by": "user",
        },
    )
    invalidate_response = client.post(
        f"/memory/{invalidated.memory_id}/events/invalidate",
        json={
            "invalidates_event_id": invalidated_event.event_id,
            "content_json": {"reason": "no longer true"},
            "created_by": "user",
        },
    )

    assert supersede_response.status_code == 200
    assert supersede_response.json()["data"]["event_type"] == "superseded"
    assert invalidate_response.status_code == 200
    assert invalidate_response.json()["data"]["event_type"] == "invalidated"

    superseded_index = client.get("/memory/index", params={"status": "superseded"})
    invalidated_index = client.get("/memory/index", params={"status": "invalidated"})

    assert any(item["memory_id"] == superseded.memory_id for item in superseded_index.json()["items"])
    assert any(item["memory_id"] == invalidated.memory_id for item in invalidated_index.json()["items"])


def test_user_rewrite_delete_and_purge_keep_user_control_semantics():
    client = TestClient(app)

    rewrite_memory = _create_memory(status="candidate")
    rewrite_response = client.post(
        f"/memory/{rewrite_memory.memory_id}/rewrite",
        json={
            "title": "User rewritten PR-2 memory",
            "content": "User controlled rewrite.",
            "status": "approved",
            "tags": ["user-control"],
            "reason": "test explicit rewrite",
        },
    )

    assert rewrite_response.status_code == 200
    rewritten = rewrite_response.json()["data"]
    assert rewritten["title"] == "User rewritten PR-2 memory"
    assert rewritten["status"] == "approved"

    delete_memory = _create_memory(status="approved")
    delete_response = client.delete(f"/memory/{delete_memory.memory_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_id"] == delete_memory.memory_id
    assert memory_repo.get(delete_memory.memory_id) is None

    purge_memory = _create_memory(status="approved")
    purge_response = client.post(
        "/memory/purge",
        json={
            "confirm": True,
            "memory_ids": [purge_memory.memory_id],
            "reason": "test explicit purge",
        },
    )

    assert purge_response.status_code == 200
    assert purge_response.json()["purged_memory_ids"] == [purge_memory.memory_id]
    assert memory_repo.get(purge_memory.memory_id) is None

    events = client.get("/memory/events")
    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()["items"]]
    assert "user_rewritten" in event_types
    assert "user_deleted" in event_types
    assert "user_purged" in event_types

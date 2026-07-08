import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import (
    Conversation,
    ConversationMessage,
    GovernorDecision,
    MemoryItem,
    Run,
    RunLogLine,
    RunStep,
    Skill,
    Task,
    TaskEventRecord,
    TaskStatus,
)
from app.services.memory_ledger import append_memory_event, record_memory_item_event
from app.store.repositories import (
    conversation_messages_repo,
    conversations_repo,
    governor_decisions_repo,
    memory_repo,
    run_logs_repo,
    run_steps_repo,
    runs_repo,
    skills_repo,
    task_events_repo,
    tasks_repo,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_exact_retrieval_resolves_supported_key_shapes():
    client = TestClient(app)
    marker = new_id("pr3")
    task_id = new_id("task")
    run_id = new_id("run")
    memory_id = new_id("mem")
    subject_key = f"task:{task_id}:fact:{memory_id}"
    decision_id = new_id("gdec")
    failure_id = f"run:{run_id}:error"

    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title=f"PR-3 exact task {marker}",
            description="Exact retrieval task fixture",
            status=TaskStatus.running,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            last_run_id=run_id,
        )
    )
    runs_repo.upsert(Run(run_id=run_id, task_id=task_id, status="running", queued_at=_now_iso()))
    run_steps_repo.upsert(
        RunStep(
            run_step_id=new_id("step"),
            run_id=run_id,
            task_id=task_id,
            sequence=2,
            step_type="execute",
            status="failed",
            failure_id=failure_id,
            decision_id=decision_id,
            created_at=_now_iso(),
        )
    )
    memory_repo.upsert(
        MemoryItem(
            memory_id=memory_id,
            memory_type="test_fact",
            title=f"PR-3 exact memory {marker}",
            content="Exact retrieval memory fixture.",
            confidence=0.9,
            status="approved",
            scope_type="task",
            scope_id=task_id,
            task_id=task_id,
            created_at=_now_iso(),
        )
    )
    governor_decisions_repo.upsert(
        GovernorDecision(
            decision_id=decision_id,
            action_id=new_id("gact"),
            suggestion_id=new_id("sug"),
            decision="require_confirmation",
            reason=f"PR-3 exact decision {marker}",
            risk_level="medium",
            created_at=_now_iso(),
            source_task_id=task_id,
        )
    )
    append_memory_event(
        event_type="observed",
        memory_id=memory_id,
        subject_key=subject_key,
        task_id=task_id,
        run_id=run_id,
        decision_id=decision_id,
        failure_id=failure_id,
        content_json={"title": "PR-3 exact event", "marker": marker},
        value_json={"kind": "fact"},
        created_by="ai",
    )

    by_memory = client.post("/memory/retrieve/exact", json={"key_type": "memory_id", "key": memory_id})
    by_subject = client.post("/memory/retrieve/exact", json={"key_type": "subject_key", "key": subject_key})
    by_run = client.post("/memory/retrieve/exact", json={"key_type": "run_id", "key": run_id})
    by_decision = client.post("/memory/retrieve/exact", json={"key_type": "decision_id", "key": decision_id})
    by_failure = client.post("/memory/retrieve/exact", json={"key_type": "failure_id", "key": failure_id})

    assert by_memory.status_code == 200
    assert {item["source_type"] for item in by_memory.json()["data"]["items"]} >= {"memory", "memory_event"}
    assert by_subject.status_code == 200
    assert any(item["source_type"] == "memory_event" for item in by_subject.json()["data"]["items"])
    assert by_run.status_code == 200
    assert {item["source_type"] for item in by_run.json()["data"]["items"]} >= {"run", "run_step"}
    assert by_decision.status_code == 200
    assert any(item["source_type"] == "decision" for item in by_decision.json()["data"]["items"])
    assert by_failure.status_code == 200
    assert any(item["source_type"] == "run_step" for item in by_failure.json()["data"]["items"])


def test_native_evidence_search_covers_kane_owned_sources():
    client = TestClient(app)
    marker = new_id("pr3search")
    task_id = new_id("task")
    run_id = new_id("run")
    conversation_id = new_id("conv")
    skill_id = new_id("skill")

    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title=f"Task source {marker}",
            description=f"Native search task evidence {marker}",
            status=TaskStatus.running,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            result_summary=f"Summary evidence {marker}",
        )
    )
    task_events_repo.upsert(
        TaskEventRecord(
            event_id=new_id("evt"),
            task_id=task_id,
            type="retrieval_test",
            message=f"Task log evidence {marker}",
            created_at=_now_iso(),
        )
    )
    runs_repo.upsert(Run(run_id=run_id, task_id=task_id, status="running", queued_at=_now_iso()))
    run_logs_repo.upsert(
        RunLogLine(
            log_id=new_id("log"),
            run_id=run_id,
            seq=1,
            level="info",
            message=f"Run log evidence {marker}",
            created_at=_now_iso(),
        )
    )
    conversations_repo.upsert(
        Conversation(
            conversation_id=conversation_id,
            title=f"Conversation source {marker}",
            agent_id="builtin_octopus",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
    )
    conversation_messages_repo.upsert(
        ConversationMessage(
            message_id=new_id("msg"),
            conversation_id=conversation_id,
            role="user",
            kind="chat",
            content=f"Conversation log evidence {marker}",
            created_at=_now_iso(),
        )
    )
    skills_repo.upsert(
        Skill(
            skill_id=skill_id,
            name=f"Skill source {marker}",
            version="0.0.1",
            category="test",
            description=f"Skill evidence {marker}",
        )
    )
    append_memory_event(
        event_type="observed",
        memory_id=new_id("mem"),
        subject_key=f"test:{marker}",
        content_json={"title": "Native search event", "marker": marker},
        value_json={"summary": f"Memory event evidence {marker}"},
        evidence_refs=[f"evidence:{marker}"],
        created_by="ai",
    )

    response = client.post(
        "/memory/retrieve/search",
        json={"query": marker, "limit": 20, "max_chars": 20000},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    source_types = {item["source_type"] for item in data["items"]}
    assert {"memory_event", "run_log", "conversation_message", "task", "task_event", "skill"} <= source_types
    assert all("source_type" in item and "ref_id" in item for item in data["items"])


def test_runtime_context_uses_active_snapshot_relevant_evidence_and_current_run_context_only():
    client = TestClient(app)
    marker = new_id("pr3runtime")
    task_id = new_id("task")
    run_id = new_id("run")
    memory = MemoryItem(
        memory_id=new_id("mem"),
        memory_type="runtime_fact",
        title=f"Runtime active memory {marker}",
        content=f"Runtime active snapshot content {marker}",
        confidence=0.85,
        status="approved",
        scope_type="task",
        scope_id=task_id,
        task_id=task_id,
        created_at=_now_iso(),
    )
    memory_repo.upsert(memory)
    record_memory_item_event(memory, event_type="task_result_recorded", created_by="ai")
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title=f"Runtime context task {marker}",
            description=f"Runtime context description {marker}",
            status=TaskStatus.running,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            last_run_id=run_id,
        )
    )
    runs_repo.upsert(Run(run_id=run_id, task_id=task_id, status="running", queued_at=_now_iso()))
    run_logs_repo.upsert(
        RunLogLine(
            log_id=new_id("log"),
            run_id=run_id,
            seq=1,
            level="info",
            message=f"Runtime evidence log {marker}",
            created_at=_now_iso(),
        )
    )

    response = client.post(
        "/memory/retrieve/runtime-context",
        json={"query": marker, "task_id": task_id, "run_id": run_id, "evidence_limit": 2, "max_chars": 5000},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) == {"runtime_policy", "active_snapshot", "relevant_evidence", "current_run_context", "budget"}
    assert data["runtime_policy"]["prompt_sources"] == ["active_snapshot", "relevant_evidence", "current_run_context"]
    assert "memory_events" not in data
    assert len(data["relevant_evidence"]) <= 2
    assert data["budget"]["evidence_limit"] == 2
    assert data["current_run_context"]["run"]["run_id"] == run_id
    assert memory.memory_id in data["active_snapshot"]["memory_ids"]


def test_native_search_and_runtime_context_enforce_hard_char_budget_for_large_results():
    client = TestClient(app)
    marker = new_id("pr3budget")
    append_memory_event(
        event_type="observed",
        memory_id=new_id("mem"),
        subject_key=f"budget:{marker}",
        content_json={
            "title": "Large budget fixture",
            "body": f"{marker} " + ("x" * 12000),
        },
        value_json={"payload": "y" * 12000},
        created_by="ai",
    )

    search = client.post(
        "/memory/retrieve/search",
        json={
            "query": marker,
            "sources": ["memory_events"],
            "limit": 5,
            "max_chars": 1000,
        },
    )

    assert search.status_code == 200
    search_data = search.json()["data"]
    assert search_data["items"]
    assert search_data["budget"]["used_chars"] <= search_data["budget"]["max_chars"]
    assert search_data["budget"]["truncated"] is True
    assert any(item["truncated"] for item in search_data["items"])
    assert len(json.dumps(search_data["items"], ensure_ascii=False)) <= search_data["budget"]["max_chars"]

    runtime = client.post(
        "/memory/retrieve/runtime-context",
        json={
            "query": marker,
            "evidence_limit": 5,
            "max_chars": 1000,
        },
    )

    assert runtime.status_code == 200
    runtime_data = runtime.json()["data"]
    assert runtime_data["budget"]["evidence_used_chars"] <= runtime_data["budget"]["max_chars"]
    assert runtime_data["budget"]["evidence_truncated"] is True

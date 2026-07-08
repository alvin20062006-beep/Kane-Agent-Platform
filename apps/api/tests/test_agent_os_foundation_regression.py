from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import Run, RunStep, Task, TaskStatus
from app.store.repositories import memory_events_repo, run_steps_repo, runs_repo, tasks_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_agent_os_foundation_surfaces_remain_connected_without_side_effects():
    client = TestClient(app)
    now = _now_iso()
    task_id = new_id("task")
    run_id = new_id("run")
    run_step_id = new_id("step")
    memory_id = new_id("mem")

    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-9 Agent OS foundation regression",
            description="Cross-check execution, memory, retrieval, verifier, repair, and compiler surfaces.",
            status=TaskStatus.running,
            created_at=now,
            updated_at=now,
            last_run_id=run_id,
        )
    )
    runs_repo.upsert(
        Run(
            run_id=run_id,
            task_id=task_id,
            status="running",
            queued_at=now,
            started_at=now,
            output_excerpt="Foundation regression output excerpt.",
        )
    )
    run_steps_repo.upsert(
        RunStep(
            run_step_id=run_step_id,
            run_id=run_id,
            task_id=task_id,
            sequence=2,
            step_type="execute",
            status="failed",
            title="Foundation execute step",
            failure_id=f"failure:{run_step_id}",
            created_at=now,
            updated_at=now,
        )
    )

    steps = client.get(f"/runs/{run_id}/steps")
    assert steps.status_code == 200
    assert steps.json()["items"][0]["run_step_id"] == run_step_id

    ledger = client.post(
        "/memory/events",
        json={
            "event_type": "observed",
            "memory_id": memory_id,
            "subject_key": f"task:{task_id}:foundation",
            "task_id": task_id,
            "run_id": run_id,
            "run_step_id": run_step_id,
            "content_json": {"memory_type": "foundation_regression", "title": "Foundation regression event"},
            "value_json": {"kind": "test"},
            "evidence_refs": [f"run_step:{run_step_id}"],
            "created_by": "ai",
        },
    )
    assert ledger.status_code == 200
    initial_event_count = len(memory_events_repo.list())

    runtime_context = client.post(
        "/memory/retrieve/runtime-context",
        json={"query": "foundation", "task_id": task_id, "run_id": run_id, "max_chars": 5000},
    )
    assert runtime_context.status_code == 200
    runtime_data = runtime_context.json()["data"]
    assert runtime_data["runtime_policy"]["prompt_sources"] == [
        "active_snapshot",
        "relevant_evidence",
        "current_run_context",
    ]
    assert "memory_events" not in runtime_data

    reference = client.post(
        f"/runs/{run_id}/reference-candidates",
        json={
            "run_step_id": run_step_id,
            "agent_role": "test_reviewer",
            "summary": "Keep PR-9 as tests and documentation only.",
            "risks": ["Scope expansion"],
            "recommended_plan": ["Run baseline tests", "Document guardrails"],
            "confidence": 0.8,
            "evidence_refs": [f"memory_event:{ledger.json()['data']['event_id']}"],
        },
    )
    assert reference.status_code == 200

    aggregation = client.post(
        f"/runs/{run_id}/reference-aggregations",
        json={
            "run_step_id": run_step_id,
            "candidate_ids": [reference.json()["data"]["candidate_id"]],
            "known_gaps": ["No new feature work in PR-9."],
            "verifier_requirements": ["Run typecheck:web, test:bridge, and test:api."],
        },
    )
    assert aggregation.status_code == 200
    assert aggregation.json()["data"]["consensus"]

    verifier = client.post(
        f"/runs/{run_id}/verifier-results",
        json={
            "run_step_id": run_step_id,
            "verifier_type": "code",
            "status": "failed",
            "passed": False,
            "findings": ["Mock failed check for repair regression."],
            "check_key": "foundation_regression_check",
            "error_summary": "Mock verifier failure.",
            "evidence_refs": [f"run_step:{run_step_id}"],
        },
    )
    assert verifier.status_code == 200

    repair = client.post(
        f"/runs/{run_id}/repair-attempts",
        json={
            "run_step_id": run_step_id,
            "verifier_result_id": verifier.json()["data"]["result_id"],
            "failure_ref": f"verifier_result:{verifier.json()['data']['result_id']}",
            "failure_type": "verification_failed",
            "attempt_kind": "repair",
            "status": "proposed",
            "repair_action": "manual_review",
            "repair_key": "foundation_manual_review",
            "evidence_refs": [f"verifier_result:{verifier.json()['data']['result_id']}"],
        },
    )
    assert repair.status_code == 200

    compiler = client.post("/memory/compiler/runs", json={"run_id": run_id})
    assert compiler.status_code == 200
    compiler_data = compiler.json()
    assert compiler_data["data"]["dry_run"] is True
    assert compiler_data["candidates"]
    assert len(memory_events_repo.list()) == initial_event_count

    proposed = next(item for item in compiler_data["candidates"] if item["status"] == "proposed")
    commit = client.post(
        f"/memory/compiler/candidates/{proposed['candidate_id']}/commit",
        json={"metadata": {"test": "pr-9 foundation regression"}},
    )
    assert commit.status_code == 200
    assert commit.json()["event"]["created_by"] == "ai"
    assert len(memory_events_repo.list()) == initial_event_count + 1

    step_after = run_steps_repo.get(run_step_id)
    assert step_after is not None
    assert step_after.verification_ref == f"verifier_result:{verifier.json()['data']['result_id']}"
    assert step_after.repair_ref == f"repair_attempt:{repair.json()['data']['repair_attempt_id']}"
    assert step_after.decision_id == aggregation.json()["data"]["aggregation_id"]

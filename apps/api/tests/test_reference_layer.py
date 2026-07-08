from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import Run, RunStep, Task, TaskStatus
from app.store.repositories import run_steps_repo, runs_repo, tasks_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _create_run_with_step() -> tuple[str, str, str]:
    task_id = new_id("task")
    run_id = new_id("run")
    run_step_id = new_id("step")
    now = _now_iso()
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-4 reference layer smoke task",
            description="Exercise advisory reference candidates and aggregation.",
            status=TaskStatus.running,
            created_at=now,
            updated_at=now,
            last_run_id=run_id,
        )
    )
    runs_repo.upsert(Run(run_id=run_id, task_id=task_id, status="running", queued_at=now))
    run_steps_repo.upsert(
        RunStep(
            run_step_id=run_step_id,
            run_id=run_id,
            task_id=task_id,
            sequence=2,
            step_type="execute",
            status="running",
            title="Execute with reference review",
            created_at=now,
            updated_at=now,
        )
    )
    return task_id, run_id, run_step_id


def test_reference_candidates_can_be_created_and_read():
    _task_id, run_id, run_step_id = _create_run_with_step()
    client = TestClient(app)

    response = client.post(
        f"/runs/{run_id}/reference-candidates",
        json={
            "run_step_id": run_step_id,
            "agent_role": "architect_reviewer",
            "summary": "Keep the PR-4 surface narrow and attach outputs to RunStep references.",
            "risks": ["Scope creep into verifier work."],
            "recommended_plan": ["Persist reference candidates.", "Aggregate before execution."],
            "files_to_touch": ["apps/api/app/services/reference_layer.py"],
            "confidence": 0.82,
            "evidence_refs": [f"run_step:{run_step_id}"],
        },
    )

    assert response.status_code == 200
    candidate = response.json()["data"]
    assert candidate["agent_role"] == "architect_reviewer"
    assert candidate["summary"]
    assert candidate["risks"] == ["Scope creep into verifier work."]
    assert candidate["recommended_plan"] == ["Persist reference candidates.", "Aggregate before execution."]
    assert candidate["files_to_touch"] == ["apps/api/app/services/reference_layer.py"]
    assert candidate["confidence"] == 0.82

    listed = client.get(f"/runs/{run_id}/reference-candidates", params={"run_step_id": run_step_id})
    fetched = client.get(f"/reference-candidates/{candidate['candidate_id']}")

    assert listed.status_code == 200
    assert any(item["candidate_id"] == candidate["candidate_id"] for item in listed.json()["items"])
    assert fetched.status_code == 200
    assert fetched.json()["data"]["candidate_id"] == candidate["candidate_id"]


def test_reference_aggregator_creates_decision_and_links_run_step():
    _task_id, run_id, run_step_id = _create_run_with_step()
    client = TestClient(app)

    candidate_payloads = [
        {
            "run_step_id": run_step_id,
            "agent_role": "implementation_reviewer",
            "summary": "Use a small service and API endpoints only.",
            "risks": [],
            "recommended_plan": ["Add reference service.", "Add aggregation endpoint."],
            "files_to_touch": ["apps/api/app/services/reference_layer.py", "apps/api/app/routes/v2/platform.py"],
            "confidence": 0.9,
            "evidence_refs": [f"run:{run_id}"],
        },
        {
            "run_step_id": run_step_id,
            "agent_role": "security_reviewer",
            "summary": "Do not let reference reviewers execute commands or mutate files.",
            "risks": ["Reference output must remain advisory."],
            "recommended_plan": ["Keep candidates advisory.", "Require explicit execution elsewhere."],
            "files_to_touch": [],
            "confidence": 0.72,
            "evidence_refs": [f"run_step:{run_step_id}"],
        },
        {
            "run_step_id": run_step_id,
            "agent_role": "test_reviewer",
            "summary": "Cover creation, reading, aggregation, and RunStep linkage.",
            "risks": [],
            "recommended_plan": ["Add focused API tests.", "Run baseline checks."],
            "files_to_touch": ["apps/api/tests/test_reference_layer.py"],
            "confidence": 0.86,
            "evidence_refs": [],
        },
    ]
    candidate_ids: list[str] = []
    for payload in candidate_payloads:
        response = client.post(f"/runs/{run_id}/reference-candidates", json=payload)
        assert response.status_code == 200
        candidate_ids.append(response.json()["data"]["candidate_id"])

    aggregation_response = client.post(
        f"/runs/{run_id}/reference-aggregations",
        json={
            "run_step_id": run_step_id,
            "candidate_ids": candidate_ids,
            "known_gaps": ["docs_reviewer_not_collected_in_test_fixture"],
            "verifier_requirements": ["Run PR-4 baseline commands."],
        },
    )

    assert aggregation_response.status_code == 200
    decision = aggregation_response.json()["data"]
    assert set(decision["candidates_considered"]) == set(candidate_ids)
    assert decision["selected_plan"]
    assert len(decision["rejected_candidates"]) == 2
    assert "consensus" in decision and decision["consensus"]
    assert "confidence" in decision and decision["confidence"] > 0
    assert "known_gaps" in decision
    assert "verifier_requirements" in decision
    assert decision["requires_user_confirmation"] is False

    step = run_steps_repo.get(run_step_id)
    assert step is not None
    assert step.decision_id == decision["aggregation_id"]
    assert step.output_ref == f"reference_aggregation:{decision['aggregation_id']}"
    assert f"reference_aggregation:{decision['aggregation_id']}" in step.evidence_refs
    assert all(f"reference_candidate:{candidate_id}" in step.evidence_refs for candidate_id in candidate_ids)

    listed = client.get(f"/runs/{run_id}/reference-aggregations", params={"run_step_id": run_step_id})
    fetched = client.get(f"/reference-aggregations/{decision['aggregation_id']}")

    assert listed.status_code == 200
    assert any(item["aggregation_id"] == decision["aggregation_id"] for item in listed.json()["items"])
    assert fetched.status_code == 200
    assert fetched.json()["data"]["aggregation_id"] == decision["aggregation_id"]

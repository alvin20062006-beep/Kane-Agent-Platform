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
            title="PR-5 verifier interface smoke task",
            description="Exercise verifier result recording without executing commands.",
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
            sequence=3,
            step_type="summarize",
            status="running",
            title="Summarize with verification",
            created_at=now,
            updated_at=now,
        )
    )
    return task_id, run_id, run_step_id


def test_verifier_result_can_be_created_read_and_linked_to_run_step():
    _task_id, run_id, run_step_id = _create_run_with_step()
    client = TestClient(app)

    response = client.post(
        f"/runs/{run_id}/verifier-results",
        json={
            "run_step_id": run_step_id,
            "verifier_type": "code",
            "status": "passed",
            "passed": True,
            "findings": ["Mock API smoke check completed."],
            "command_key": "npm_test_api",
            "output_summary": "Mock verifier reported success.",
            "evidence_refs": [f"run_step:{run_step_id}"],
        },
    )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["run_id"] == run_id
    assert result["run_step_id"] == run_step_id
    assert result["verifier_type"] == "code"
    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["command_key"] == "npm_test_api"

    step = run_steps_repo.get(run_step_id)
    assert step is not None
    assert step.verification_ref == f"verifier_result:{result['result_id']}"
    assert f"verifier_result:{result['result_id']}" in step.evidence_refs
    assert f"run_step:{run_step_id}" in step.evidence_refs

    listed = client.get(f"/runs/{run_id}/verifier-results", params={"run_step_id": run_step_id})
    fetched = client.get(f"/verifier-results/{result['result_id']}")

    assert listed.status_code == 200
    assert any(item["result_id"] == result["result_id"] for item in listed.json()["items"])
    assert fetched.status_code == 200
    assert fetched.json()["data"]["result_id"] == result["result_id"]


def test_verifier_result_can_express_failed_blocked_and_skipped_states():
    _task_id, run_id, run_step_id = _create_run_with_step()
    client = TestClient(app)

    payloads = [
        {
            "run_step_id": run_step_id,
            "verifier_type": "security",
            "status": "failed",
            "passed": False,
            "check_key": "secrets_scan_mock",
            "error_summary": "Mock check found a policy violation.",
            "findings": ["Potential secret handling issue."],
        },
        {
            "run_step_id": run_step_id,
            "verifier_type": "bridge",
            "status": "blocked",
            "check_key": "local_bridge_health",
            "error_summary": "Bridge health check was unavailable in mock fixture.",
        },
        {
            "run_step_id": run_step_id,
            "verifier_type": "docs",
            "status": "skipped",
            "check_key": "docs_review",
            "output_summary": "Docs verifier skipped for this mock fixture.",
        },
    ]

    for payload in payloads:
        response = client.post(f"/runs/{run_id}/verifier-results", json=payload)
        assert response.status_code == 200
        assert response.json()["data"]["passed"] is False

    listed = client.get(f"/runs/{run_id}/verifier-results")

    assert listed.status_code == 200
    statuses = {item["status"] for item in listed.json()["items"]}
    verifier_types = {item["verifier_type"] for item in listed.json()["items"]}
    assert {"failed", "blocked", "skipped"} <= statuses
    assert {"security", "bridge", "docs"} <= verifier_types


def test_verifier_result_rejects_shell_like_command_keys_and_fake_passes():
    _task_id, run_id, run_step_id = _create_run_with_step()
    client = TestClient(app)

    shell_like = client.post(
        f"/runs/{run_id}/verifier-results",
        json={
            "run_step_id": run_step_id,
            "verifier_type": "manual",
            "status": "passed",
            "passed": True,
            "command_key": "npm run test:api",
            "output_summary": "This should be rejected because it is a shell string.",
        },
    )
    fake_pass = client.post(
        f"/runs/{run_id}/verifier-results",
        json={
            "run_step_id": run_step_id,
            "verifier_type": "manual",
            "status": "failed",
            "passed": True,
            "check_key": "manual_review",
            "error_summary": "A failed check cannot also pass.",
        },
    )
    unsupported_success = client.post(
        f"/runs/{run_id}/verifier-results",
        json={
            "run_step_id": run_step_id,
            "verifier_type": "manual",
            "status": "passed",
            "passed": True,
            "check_key": "manual_review",
        },
    )

    assert shell_like.status_code == 400
    assert fake_pass.status_code == 400
    assert unsupported_success.status_code == 400

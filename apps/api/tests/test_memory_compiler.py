from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import RepairAttempt, Run, RunStep, Task, TaskStatus, VerifierResult
from app.store.repositories import (
    memory_events_repo,
    repair_attempts_repo,
    run_steps_repo,
    runs_repo,
    tasks_repo,
    verifier_results_repo,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _create_run_fixture(
    *,
    run_status: str = "succeeded",
    step_status: str = "succeeded",
    output_excerpt: str | None = "PR-7 compiler task result.",
) -> tuple[str, str, str]:
    task_id = new_id("task")
    run_id = new_id("run")
    run_step_id = new_id("step")
    now = _now_iso()
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-7 memory compiler smoke task",
            description="Exercise Background Memory Compiler candidate flow.",
            status=TaskStatus.succeeded if run_status == "succeeded" else TaskStatus.failed,
            created_at=now,
            updated_at=now,
            last_run_id=run_id,
        )
    )
    runs_repo.upsert(
        Run(
            run_id=run_id,
            task_id=task_id,
            status=run_status,  # type: ignore[arg-type]
            queued_at=now,
            started_at=now,
            finished_at=now,
            output_excerpt=output_excerpt,
        )
    )
    run_steps_repo.upsert(
        RunStep(
            run_step_id=run_step_id,
            run_id=run_id,
            task_id=task_id,
            sequence=2,
            step_type="execute",
            status=step_status,  # type: ignore[arg-type]
            title="Execute for compiler",
            created_at=now,
            updated_at=now,
        )
    )
    return task_id, run_id, run_step_id


def _add_failed_verifier(task_id: str, run_id: str, run_step_id: str) -> str:
    verifier_result_id = new_id("ver")
    verifier_results_repo.upsert(
        VerifierResult(
            result_id=verifier_result_id,
            run_id=run_id,
            run_step_id=run_step_id,
            task_id=task_id,
            verifier_type="code",
            status="failed",
            passed=False,
            findings=["Compiler should preserve this as evidence, not prompt memory."],
            check_key="mock_pr7_check",
            error_summary="Mock verifier failure.",
            evidence_refs=[f"run_step:{run_step_id}"],
            created_at=_now_iso(),
        )
    )
    return verifier_result_id


def test_memory_compiler_dry_run_persists_candidates_without_appending_events():
    task_id, run_id, run_step_id = _create_run_fixture()
    _add_failed_verifier(task_id, run_id, run_step_id)
    client = TestClient(app)

    response = client.post("/memory/compiler/runs", json={"run_id": run_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["candidates_created"] >= 2
    candidate_types = {candidate["candidate_type"] for candidate in payload["candidates"]}
    assert {"task_result_recorded", "verification_recorded"} <= candidate_types
    assert [event for event in memory_events_repo.list() if event.run_id == run_id] == []

    listed = client.get("/memory/compiler/candidates", params={"run_id": run_id})
    assert listed.status_code == 200
    assert all(item["status"] == "proposed" for item in listed.json()["items"])


def test_memory_compiler_candidate_commit_appends_event_and_updates_projection():
    _task_id, run_id, _run_step_id = _create_run_fixture(output_excerpt="Compiler commit result.")
    client = TestClient(app)

    compiler_response = client.post("/memory/compiler/runs", json={"run_id": run_id})
    assert compiler_response.status_code == 200
    task_result = next(
        candidate
        for candidate in compiler_response.json()["candidates"]
        if candidate["candidate_type"] == "task_result_recorded"
    )

    commit_response = client.post(
        f"/memory/compiler/candidates/{task_result['candidate_id']}/commit",
        json={"metadata": {"test": "pr-7 commit"}},
    )

    assert commit_response.status_code == 200
    committed = commit_response.json()["data"]
    event = commit_response.json()["event"]
    assert committed["status"] == "committed"
    assert committed["committed_event_id"] == event["event_id"]
    assert event["event_type"] == "task_result_recorded"
    assert event["created_by"] == "ai"
    assert event["metadata"]["compiler_candidate_id"] == task_result["candidate_id"]

    index = client.get("/memory/index", params={"status": "active"})
    assert index.status_code == 200
    assert any(item["memory_id"] == task_result["memory_id"] for item in index.json()["items"])
    snapshot = client.get("/memory/snapshot")
    assert snapshot.status_code == 200
    assert task_result["memory_id"] in snapshot.json()["data"]["memory_ids"]


def test_memory_compiler_avoids_retry_spam_and_requires_explicit_candidate_commit():
    task_id, run_id, run_step_id = _create_run_fixture(run_status="failed", step_status="failed", output_excerpt=None)
    verifier_result_id = _add_failed_verifier(task_id, run_id, run_step_id)
    now = _now_iso()
    proposed_retry_id = new_id("repair")
    blocked_retry_id = new_id("repair")
    repair_attempts_repo.upsert(
        RepairAttempt(
            repair_attempt_id=proposed_retry_id,
            run_id=run_id,
            run_step_id=run_step_id,
            task_id=task_id,
            verifier_result_id=verifier_result_id,
            failure_ref=f"verifier_result:{verifier_result_id}",
            failure_type="bridge_timeout",
            attempt_index=1,
            attempt_kind="retry",
            status="proposed",
            repair_action="retry_same_inputs",
            repair_key="retry_bridge_timeout",
            loop_event="retry_proposed",
            evidence_refs=[f"verifier_result:{verifier_result_id}"],
            created_at=now,
        )
    )
    repair_attempts_repo.upsert(
        RepairAttempt(
            repair_attempt_id=blocked_retry_id,
            run_id=run_id,
            run_step_id=run_step_id,
            task_id=task_id,
            verifier_result_id=verifier_result_id,
            failure_ref=f"verifier_result:{verifier_result_id}",
            failure_type="bridge_timeout",
            attempt_index=2,
            attempt_kind="retry",
            status="blocked",
            repair_action="retry_same_inputs",
            repair_key="retry_bridge_timeout",
            loop_event="retry_blocked",
            needs_user_confirmation=True,
            safety_status="needs_user_confirmation",
            evidence_refs=[f"verifier_result:{verifier_result_id}"],
            created_at=now,
            metadata={"block_reason": "repeated_failure_type"},
        )
    )
    client = TestClient(app)

    rejected = client.post("/memory/compiler/runs", json={"run_id": run_id, "dry_run": False})
    response = client.post("/memory/compiler/runs", json={"run_id": run_id})

    assert rejected.status_code == 400
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    source_ids = {candidate["source_id"] for candidate in candidates}
    assert blocked_retry_id in source_ids
    assert proposed_retry_id not in source_ids
    assert any(candidate["candidate_type"] == "failure_recorded" for candidate in candidates)

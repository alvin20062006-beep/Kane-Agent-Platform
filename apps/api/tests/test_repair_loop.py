from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.id_utils import new_id
from app.main import app
from app.models import Run, RunStep, Task, TaskStatus, VerifierResult
from app.store.repositories import run_steps_repo, runs_repo, tasks_repo, verifier_results_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _create_run_step_with_verifier(*, status: str = "failed") -> tuple[str, str, str, str]:
    task_id = new_id("task")
    run_id = new_id("run")
    run_step_id = new_id("step")
    verifier_result_id = new_id("ver")
    now = _now_iso()
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-6 repair loop smoke task",
            description="Exercise retry and repair evidence recording.",
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
            status="failed",
            title="Execute with repair",
            failure_id=f"failure:{run_step_id}",
            created_at=now,
            updated_at=now,
        )
    )
    verifier_results_repo.upsert(
        VerifierResult(
            result_id=verifier_result_id,
            run_id=run_id,
            run_step_id=run_step_id,
            task_id=task_id,
            verifier_type="code",
            status=status,  # type: ignore[arg-type]
            passed=status == "passed",
            findings=["Mock verifier finding."],
            check_key="mock_check",
            output_summary="Mock verifier passed." if status == "passed" else None,
            error_summary="Mock verifier failed." if status != "passed" else None,
            evidence_refs=[f"run_step:{run_step_id}"],
            created_at=now,
        )
    )
    return task_id, run_id, run_step_id, verifier_result_id


def test_repair_attempt_can_be_created_read_and_linked_to_run_step():
    _task_id, run_id, run_step_id, verifier_result_id = _create_run_step_with_verifier()
    client = TestClient(app)

    response = client.post(
        f"/runs/{run_id}/repair-attempts",
        json={
            "run_step_id": run_step_id,
            "verifier_result_id": verifier_result_id,
            "failure_id": f"failure:{run_step_id}",
            "failure_ref": f"verifier_result:{verifier_result_id}",
            "failure_type": "verification_failed",
            "attempt_kind": "repair",
            "status": "proposed",
            "repair_action": "adjust_prompt",
            "repair_key": "prompt_strategy_update",
            "evidence_refs": [f"verifier_result:{verifier_result_id}"],
        },
    )

    assert response.status_code == 200
    attempt = response.json()["data"]
    assert attempt["run_id"] == run_id
    assert attempt["run_step_id"] == run_step_id
    assert attempt["verifier_result_id"] == verifier_result_id
    assert attempt["status"] == "proposed"
    assert attempt["loop_event"] == "repair_proposed"

    step = run_steps_repo.get(run_step_id)
    assert step is not None
    assert step.repair_ref == f"repair_attempt:{attempt['repair_attempt_id']}"
    assert f"repair_attempt:{attempt['repair_attempt_id']}" in step.evidence_refs
    assert step.metadata["latest_repair_status"] == "proposed"
    assert step.metadata["latest_repair_loop_event"] == "repair_proposed"

    listed = client.get(f"/runs/{run_id}/repair-attempts", params={"run_step_id": run_step_id})
    fetched = client.get(f"/repair-attempts/{attempt['repair_attempt_id']}")

    assert listed.status_code == 200
    assert any(item["repair_attempt_id"] == attempt["repair_attempt_id"] for item in listed.json()["items"])
    assert fetched.status_code == 200
    assert fetched.json()["data"]["repair_attempt_id"] == attempt["repair_attempt_id"]


def test_retry_limit_is_per_run_step_and_blocks_fourth_retry():
    _task_id, run_id, run_step_id, verifier_result_id = _create_run_step_with_verifier()
    client = TestClient(app)
    failure_types = ["validation_error", "permission_denied", "api_unreachable", "tool_execution_failed"]

    responses = []
    for failure_type in failure_types:
        responses.append(
            client.post(
                f"/runs/{run_id}/repair-attempts",
                json={
                    "run_step_id": run_step_id,
                    "verifier_result_id": verifier_result_id,
                    "failure_ref": f"verifier_result:{verifier_result_id}",
                    "failure_type": failure_type,
                    "attempt_kind": "retry",
                    "status": "proposed",
                    "repair_action": "retry_same_inputs",
                    "repair_key": f"retry_{failure_type}",
                },
            )
        )

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert [response.json()["data"]["status"] for response in responses] == ["proposed", "proposed", "proposed", "blocked"]
    blocked = responses[-1].json()["data"]
    assert blocked["needs_user_confirmation"] is True
    assert blocked["metadata"]["block_reason"] == "retry_limit_exceeded"

    step = run_steps_repo.get(run_step_id)
    assert step is not None
    assert step.retry_count == 3
    assert len(step.retry_history) == 4

    _other_task_id, other_run_id, other_step_id, other_verifier_id = _create_run_step_with_verifier()
    other = client.post(
        f"/runs/{other_run_id}/repair-attempts",
        json={
            "run_step_id": other_step_id,
            "verifier_result_id": other_verifier_id,
            "failure_ref": f"verifier_result:{other_verifier_id}",
            "failure_type": "validation_error",
            "attempt_kind": "retry",
            "status": "proposed",
            "repair_action": "retry_same_inputs",
            "repair_key": "retry_validation_error",
        },
    )
    assert other.status_code == 200
    assert other.json()["data"]["status"] == "proposed"
    assert run_steps_repo.get(other_step_id).retry_count == 1  # type: ignore[union-attr]


def test_repeated_failure_type_escalates_to_blocked_confirmation():
    _task_id, run_id, run_step_id, verifier_result_id = _create_run_step_with_verifier()
    client = TestClient(app)
    payload = {
        "run_step_id": run_step_id,
        "verifier_result_id": verifier_result_id,
        "failure_ref": f"verifier_result:{verifier_result_id}",
        "failure_type": "bridge_timeout",
        "attempt_kind": "retry",
        "status": "proposed",
        "repair_action": "retry_same_inputs",
        "repair_key": "retry_bridge_timeout",
    }

    first = client.post(f"/runs/{run_id}/repair-attempts", json=payload)
    second = client.post(f"/runs/{run_id}/repair-attempts", json=payload)

    assert first.status_code == 200
    assert first.json()["data"]["status"] == "proposed"
    assert second.status_code == 200
    blocked = second.json()["data"]
    assert blocked["status"] == "blocked"
    assert blocked["needs_user_confirmation"] is True
    assert blocked["metadata"]["block_reason"] == "repeated_failure_type"


def test_high_risk_repair_blocks_and_shell_like_keys_are_rejected():
    _task_id, run_id, run_step_id, verifier_result_id = _create_run_step_with_verifier()
    client = TestClient(app)

    high_risk = client.post(
        f"/runs/{run_id}/repair-attempts",
        json={
            "run_step_id": run_step_id,
            "verifier_result_id": verifier_result_id,
            "failure_ref": f"verifier_result:{verifier_result_id}",
            "failure_type": "permission_denied",
            "attempt_kind": "repair",
            "status": "approved",
            "repair_action": "switch_tool",
            "repair_key": "local_write_tool",
            "high_risk": True,
        },
    )
    shell_like = client.post(
        f"/runs/{run_id}/repair-attempts",
        json={
            "run_step_id": run_step_id,
            "verifier_result_id": verifier_result_id,
            "failure_ref": f"verifier_result:{verifier_result_id}",
            "failure_type": "tool_execution_failed",
            "attempt_kind": "repair",
            "status": "proposed",
            "repair_action": "manual_review",
            "action_key": "python -m pytest",
        },
    )

    assert high_risk.status_code == 200
    blocked = high_risk.json()["data"]
    assert blocked["status"] == "blocked"
    assert blocked["safety_status"] == "needs_user_confirmation"
    assert blocked["needs_user_confirmation"] is True
    assert blocked["metadata"]["action_execution"] == "not_executed"
    assert shell_like.status_code == 400


def test_repair_statuses_and_trace_rollback_are_recordable_without_side_effects():
    _task_id, run_id, run_step_id, verifier_result_id = _create_run_step_with_verifier()
    client = TestClient(app)
    statuses = ["approved", "running", "succeeded", "failed", "skipped"]

    for status in statuses:
        response = client.post(
            f"/runs/{run_id}/repair-attempts",
            json={
                "run_step_id": run_step_id,
                "verifier_result_id": verifier_result_id,
                "failure_ref": f"verifier_result:{verifier_result_id}",
                "failure_type": "verification_failed",
                "attempt_kind": "repair",
                "status": status,
                "repair_action": "manual_review",
                "repair_key": f"manual_{status}",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["metadata"]["action_execution"] == "not_executed"

    rollback = client.post(
        f"/runs/{run_id}/repair-attempts",
        json={
            "run_step_id": run_step_id,
            "verifier_result_id": verifier_result_id,
            "failure_ref": f"verifier_result:{verifier_result_id}",
            "failure_type": "verification_failed",
            "attempt_kind": "trace_rollback",
            "status": "rollback_proposed",
            "repair_action": "trace_rollback",
            "repair_key": "trace_rollback_only",
        },
    )

    assert rollback.status_code == 200
    assert rollback.json()["data"]["loop_event"] == "rollback_proposed"

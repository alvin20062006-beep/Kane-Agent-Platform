from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.executor import ExecuteResult
from app.id_utils import new_id
from app.main import app
from app.models import Agent, AgentStatus, Run, RunStep, Task, TaskStatus
from app.services.runtime_audit import append_watchdog_issue
from app.services.run_steps import complete_run_timeline, ensure_base_run_steps
from app.services.control_plane_agents import start_agent_test_run
from app.services.task_status_reconciliation import reconcile_all_tasks_with_latest_runs
from app.services.task_lifecycle import run_task
from app.services.worker_queue import _execute_run, _expire_stale_pending_runs, enqueue_run, stop_worker_thread
from app.store.repositories import agents_repo, run_steps_repo, runs_repo, tasks_repo
from app.store.run_step_queries import list_steps_for_run


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_run_can_be_persisted():
    run = Run(
        run_id=new_id("run"),
        task_id=new_id("task"),
        status="pending",
        queued_at=_now_iso(),
    )

    runs_repo.upsert(run)

    persisted = runs_repo.get(run.run_id)
    assert persisted is not None
    assert persisted.run_id == run.run_id
    assert persisted.task_id == run.task_id


def test_run_step_can_be_persisted():
    run_id = new_id("run")
    step = RunStep(
        run_step_id=new_id("step"),
        run_id=run_id,
        task_id=new_id("task"),
        sequence=1,
        step_type="plan",
        status="succeeded",
        title="Plan execution attempt",
        created_at=_now_iso(),
    )

    run_steps_repo.upsert(step)

    steps, total = list_steps_for_run(run_id)
    assert total >= 1
    assert any(item.run_step_id == step.run_step_id for item in steps)


def test_legacy_enqueue_run_writes_base_steps_and_steps_are_readable():
    agent_id = new_id("agent")
    task_id = new_id("task")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="PR-1 loop smoke agent",
            type="builtin",
            status=AgentStatus.idle,
            adapter_id="builtin_octopus",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="simulate_fail PR-1 loop state smoke",
            description="Exercise the legacy enqueue run path without external adapters.",
            status=TaskStatus.assigned,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            correlation_id=new_id("corr"),
        )
    )

    run = enqueue_run(task_id, agent_id)

    assert run.task_id == task_id
    steps, total = list_steps_for_run(run.run_id)
    assert total == 3
    assert [step.step_type for step in steps] == ["plan", "execute", "summarize"]

    client = TestClient(app)
    response = client.get(f"/runs/{run.run_id}/steps")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["step_type"] for item in body["items"]] == ["plan", "execute", "summarize"]


def test_builtin_worker_success_converges_terminal_run_steps(monkeypatch):
    stop_worker_thread()
    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="PR-H2 builtin success agent",
            type="builtin",
            status=AgentStatus.idle,
            adapter_id="builtin_octopus",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-H2 builtin success convergence",
            description="No source changes.",
            status=TaskStatus.assigned,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            correlation_id=new_id("corr"),
        )
    )
    run = Run(run_id=run_id, task_id=task_id, agent_id=agent_id, status="pending", queued_at=now)
    runs_repo.upsert(run)

    def fake_builtin(task, run, agent):  # noqa: ANN001
        return ExecuteResult(
            integration_path="builtin_sync",
            ok=True,
            output="PR-H2 builtin success output",
            error=None,
            meta={"test": "terminal_convergence"},
        )

    monkeypatch.setattr("app.services.worker_queue.execute_builtin_octopus", fake_builtin)

    _execute_run(run_id)

    task_after = tasks_repo.get(task_id)
    run_after = runs_repo.get(run_id)
    steps, _total = list_steps_for_run(run_id)

    assert task_after is not None
    assert task_after.status == TaskStatus.succeeded
    assert run_after is not None
    assert run_after.status == "succeeded"
    assert {step.step_type: step.status for step in steps} == {
        "plan": "succeeded",
        "execute": "succeeded",
        "summarize": "succeeded",
    }


def test_builtin_worker_finalizes_steps_before_terminal_task_status(monkeypatch):
    stop_worker_thread()
    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="V2 release ordering agent",
            type="builtin",
            status=AgentStatus.idle,
            adapter_id="builtin_octopus",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="V2 release terminal ordering",
            description="No source changes.",
            status=TaskStatus.assigned,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            correlation_id=new_id("corr"),
        )
    )
    run = Run(run_id=run_id, task_id=task_id, agent_id=agent_id, status="pending", queued_at=now)
    runs_repo.upsert(run)

    def fake_builtin(task, run, agent):  # noqa: ANN001
        return ExecuteResult(
            integration_path="builtin_sync",
            ok=True,
            output="V2 release ordering output",
            error=None,
            meta={"test": "terminal_ordering"},
        )

    status_seen_during_timeline: list[TaskStatus | str | None] = []

    def recording_complete_timeline(run_id_arg: str, *, succeeded: bool) -> None:
        observed_task = tasks_repo.get(task_id)
        status_seen_during_timeline.append(observed_task.status if observed_task else None)
        complete_run_timeline(run_id_arg, succeeded=succeeded)

    monkeypatch.setattr("app.services.worker_queue.execute_builtin_octopus", fake_builtin)
    monkeypatch.setattr("app.services.worker_queue.complete_run_timeline", recording_complete_timeline)

    _execute_run(run_id)

    task_after = tasks_repo.get(task_id)
    steps, _total = list_steps_for_run(run_id)

    assert status_seen_during_timeline
    assert status_seen_during_timeline[-1] == TaskStatus.running
    assert task_after is not None
    assert task_after.status == TaskStatus.succeeded
    assert {step.step_type: step.status for step in steps}["summarize"] == "succeeded"


def test_bridge_failure_sets_task_failed_and_terminal_steps(monkeypatch):
    stop_worker_thread()
    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="PR-H2 codex failure agent",
            type="external",
            status=AgentStatus.idle,
            adapter_id="codex_cli",
            integration_mode="external",
            integration_channels=["cli"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="PR-H2 Codex WinError failure",
            description="Simulate a permission failure from the bridge path.",
            status=TaskStatus.assigned,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            correlation_id=new_id("corr"),
        )
    )
    run = Run(run_id=run_id, task_id=task_id, agent_id=agent_id, status="pending", queued_at=now)
    runs_repo.upsert(run)

    def fake_bridge(task, run, agent):  # noqa: ANN001
        return ExecuteResult(
            integration_path="local_bridge_http",
            ok=False,
            output=None,
            error="WinError 5: Access is denied",
            meta={"error_type": "PermissionError"},
        )

    monkeypatch.setattr("app.services.worker_queue.execute_via_local_bridge", fake_bridge)

    _execute_run(run_id)

    task_after = tasks_repo.get(task_id)
    run_after = runs_repo.get(run_id)
    steps, _total = list_steps_for_run(run_id)

    assert task_after is not None
    assert task_after.status == TaskStatus.failed
    assert task_after.status != TaskStatus.assigned
    assert task_after.last_error == "WinError 5: Access is denied"
    assert run_after is not None
    assert run_after.status == "failed"
    assert run_after.error == "WinError 5: Access is denied"
    assert all(step.status in {"succeeded", "failed", "blocked", "skipped"} for step in steps)
    assert {step.step_type: step.status for step in steps}["execute"] == "failed"


def test_duplicate_run_request_reconciles_terminal_run_without_using_steps():
    stop_worker_thread()
    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="RC-1 duplicate reconcile agent",
            type="builtin",
            status=AgentStatus.idle,
            adapter_id="builtin_octopus",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="RC-1 queued task with terminal run",
            description="Task should reconcile from the terminal run.",
            status=TaskStatus.queued,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            last_run_id=run_id,
            correlation_id=new_id("corr"),
        )
    )
    run = Run(
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        status="succeeded",
        queued_at=now,
        started_at=now,
        finished_at=now,
        integration_path="builtin_sync",
        output_excerpt="terminal run output",
        output_snapshot={"status": "succeeded", "output": "terminal run output"},
    )
    runs_repo.upsert(run)
    ensure_base_run_steps(run)
    complete_run_timeline(run_id, succeeded=True)

    result = run_task(task_id)

    task_after = tasks_repo.get(task_id)
    steps, _total = list_steps_for_run(run_id)
    assert result["duplicate_request"] is True
    assert task_after is not None
    assert task_after.status == TaskStatus.succeeded
    assert {step.step_type: step.status for step in steps} == {
        "plan": "succeeded",
        "execute": "succeeded",
        "summarize": "succeeded",
    }


def test_startup_reconciliation_converges_legacy_terminal_runs_and_steps():
    stop_worker_thread()
    now = _now_iso()

    success_task_id = new_id("task")
    success_run_id = new_id("run")
    tasks_repo.upsert(
        Task(
            task_id=success_task_id,
            title="V2 legacy queued success",
            description="Terminal run should reconcile task status.",
            status=TaskStatus.queued,
            created_at=now,
            updated_at=now,
            last_run_id=success_run_id,
            correlation_id=new_id("corr"),
        )
    )
    success_run = Run(
        run_id=success_run_id,
        task_id=success_task_id,
        status="succeeded",
        queued_at=now,
        started_at=now,
        finished_at=now,
        output_excerpt="legacy success",
        output_snapshot={"status": "succeeded", "output": "legacy success"},
    )
    runs_repo.upsert(success_run)
    ensure_base_run_steps(success_run)

    failed_task_id = new_id("task")
    failed_run_id = new_id("run")
    tasks_repo.upsert(
        Task(
            task_id=failed_task_id,
            title="V2 legacy assigned failure",
            description="Terminal failure should not remain assigned.",
            status=TaskStatus.assigned,
            created_at=now,
            updated_at=now,
            last_run_id=failed_run_id,
            correlation_id=new_id("corr"),
        )
    )
    failed_run = Run(
        run_id=failed_run_id,
        task_id=failed_task_id,
        status="failed",
        queued_at=now,
        started_at=now,
        finished_at=now,
        error="PermissionError: [WinError 5] Access is denied",
        output_snapshot={"status": "failed", "error": "PermissionError: [WinError 5] Access is denied"},
    )
    runs_repo.upsert(failed_run)
    ensure_base_run_steps(failed_run)

    summary = reconcile_all_tasks_with_latest_runs(source="test_startup_reconciliation")

    success_task = tasks_repo.get(success_task_id)
    failed_task = tasks_repo.get(failed_task_id)
    success_steps, _success_total = list_steps_for_run(success_run_id)
    failed_steps, _failed_total = list_steps_for_run(failed_run_id)

    assert summary["tasks_reconciled"] >= 2
    assert success_task is not None
    assert success_task.status == TaskStatus.succeeded
    assert failed_task is not None
    assert failed_task.status == TaskStatus.failed
    assert failed_task.needs_attention is True
    assert {step.step_type: step.status for step in success_steps} == {
        "plan": "succeeded",
        "execute": "succeeded",
        "summarize": "succeeded",
    }
    assert {step.step_type: step.status for step in failed_steps} == {
        "plan": "succeeded",
        "execute": "failed",
        "summarize": "succeeded",
    }


def test_cursor_handoff_sets_waiting_approval_without_succeeding_task(monkeypatch):
    stop_worker_thread()
    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="RC-1 cursor handoff agent",
            type="external",
            status=AgentStatus.idle,
            adapter_id="cursor_cli",
            integration_mode="external",
            integration_channels=["handoff_file"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=task_id,
            title="RC-1 Cursor handoff",
            description="Only create a handoff file.",
            status=TaskStatus.assigned,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            correlation_id=new_id("corr"),
        )
    )
    runs_repo.upsert(Run(run_id=run_id, task_id=task_id, agent_id=agent_id, status="pending", queued_at=now))

    def fake_bridge(task, run, agent):  # noqa: ANN001
        return ExecuteResult(
            integration_path="cursor_handoff_file",
            ok=True,
            output="handoff file created",
            error=None,
            meta={"handoff_path": "tmp-smoke-output/cursor-handoff.md"},
            pending_handoff=True,
        )

    monkeypatch.setattr("app.services.worker_queue.execute_via_local_bridge", fake_bridge)

    _execute_run(run_id)

    task_after = tasks_repo.get(task_id)
    run_after = runs_repo.get(run_id)
    assert task_after is not None
    assert task_after.status == TaskStatus.waiting_approval
    assert task_after.status != TaskStatus.succeeded
    assert run_after is not None
    assert run_after.status == "running"
    assert run_after.output_snapshot is not None
    assert run_after.output_snapshot["status"] == "pending_handoff"


def test_permission_denied_fixer_does_not_return_task_to_assigned():
    stop_worker_thread()
    from app.services.runtime_supervision import run_fixer_once

    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="RC-1 permission denied agent",
            type="external",
            status=AgentStatus.idle,
            adapter_id="codex_cli",
            integration_mode="external",
            integration_channels=["cli"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    task = Task(
        task_id=task_id,
        title="RC-1 permission denied failure",
        description="Permission failure should require attention.",
        status=TaskStatus.failed,
        assigned_agent_id=agent_id,
        created_at=now,
        updated_at=now,
        last_run_id=run_id,
        last_error="PermissionError: [WinError 5] Access is denied",
        result_payload={"meta": {"error_type": "PermissionError", "error_kind": "permission_denied", "winerror": 5}},
        correlation_id=new_id("corr"),
    )
    tasks_repo.upsert(task)
    runs_repo.upsert(
        Run(
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            status="failed",
            queued_at=now,
            started_at=now,
            finished_at=now,
            error="PermissionError: [WinError 5] Access is denied",
            output_snapshot={"status": "failed", "meta": {"error_kind": "permission_denied", "winerror": 5}},
        )
    )
    append_watchdog_issue(
        "task_failed",
        "Codex task failed with PermissionError",
        severity="error",
        task=task,
        run_id=run_id,
        raw_error="PermissionError: [WinError 5] Access is denied",
        suggested_action="retry_run",
    )

    emitted = run_fixer_once()

    task_after = tasks_repo.get(task_id)
    assert task_after is not None
    assert task_after.status == TaskStatus.failed
    assert task_after.status != TaskStatus.assigned
    assert task_after.needs_attention is True
    assert any(event.type == "fixer_defer_permission_denied" for event in emitted)


def test_queue_timeout_fixer_does_not_return_task_to_assigned():
    stop_worker_thread()
    from app.services.runtime_supervision import run_fixer_once

    agent_id = new_id("agent")
    task_id = new_id("task")
    run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="V2 queue timeout agent",
            type="external",
            status=AgentStatus.idle,
            adapter_id="cursor_cli",
            integration_mode="external",
            integration_channels=["handoff_file"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    task = Task(
        task_id=task_id,
        title="V2 queue timeout failure",
        description="Queue timeout should require manual retry.",
        status=TaskStatus.failed,
        assigned_agent_id=agent_id,
        created_at=now,
        updated_at=now,
        last_run_id=run_id,
        last_error="queue_timeout",
        correlation_id=new_id("corr"),
    )
    tasks_repo.upsert(task)
    runs_repo.upsert(
        Run(
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            status="failed",
            queued_at=now,
            started_at=now,
            finished_at=now,
            error="queue_timeout",
            output_snapshot={"status": "failed", "error": "queue_timeout"},
        )
    )
    append_watchdog_issue(
        "task_worker_stalled",
        "Queued run exceeded timeout",
        severity="warn",
        task=task,
        run_id=run_id,
        raw_error="queue_timeout",
        suggested_action="retry_run",
    )

    emitted = run_fixer_once()

    task_after = tasks_repo.get(task_id)
    assert task_after is not None
    assert task_after.status == TaskStatus.failed
    assert task_after.status != TaskStatus.assigned
    assert task_after.needs_attention is True
    assert any(event.type == "fixer_defer_queue_timeout" for event in emitted)


def test_agent_test_run_blocked_by_existing_handoff_is_not_left_queued():
    stop_worker_thread()
    agent_id = new_id("agent")
    blocker_task_id = new_id("task")
    blocker_run_id = new_id("run")
    now = _now_iso()
    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="RC-1 cursor handoff blocker",
            type="external",
            status=AgentStatus.idle,
            adapter_id="cursor_cli",
            integration_mode="external",
            integration_channels=["handoff_file"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=blocker_task_id,
            title="Existing cursor handoff",
            description="Already waiting for human approval.",
            status=TaskStatus.waiting_approval,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            last_run_id=blocker_run_id,
            correlation_id=new_id("corr"),
        )
    )
    runs_repo.upsert(
        Run(
            run_id=blocker_run_id,
            task_id=blocker_task_id,
            agent_id=agent_id,
            status="running",
            queued_at=now,
            started_at=now,
            output_snapshot={"status": "pending_handoff"},
        )
    )

    result = start_agent_test_run(agent_id)
    task_after = tasks_repo.get(result["task_id"])
    run_after = runs_repo.get(result["run_id"])
    steps, _total = list_steps_for_run(result["run_id"])

    assert task_after is not None
    assert task_after.status == TaskStatus.failed
    assert task_after.needs_attention is True
    assert "agent_handoff_already_waiting_approval" in (task_after.last_error or "")
    assert run_after is not None
    assert run_after.status == "failed"
    assert {step.step_type: step.status for step in steps} == {
        "plan": "succeeded",
        "execute": "blocked",
        "summarize": "skipped",
    }


def test_stale_pending_run_times_out_even_when_agent_has_active_handoff():
    stop_worker_thread()
    agent_id = new_id("agent")
    blocker_task_id = new_id("task")
    blocker_run_id = new_id("run")
    stale_task_id = new_id("task")
    stale_run_id = new_id("run")
    now = _now_iso()
    old = (datetime.now(tz=timezone.utc) - timedelta(minutes=11)).isoformat()

    agents_repo.upsert(
        Agent(
            agent_id=agent_id,
            display_name="V2 stale queue cursor agent",
            type="external",
            status=AgentStatus.idle,
            adapter_id="cursor_cli",
            integration_mode="external",
            integration_channels=["handoff_file"],
            control_depth="assisted",
            last_heartbeat_at=now,
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=blocker_task_id,
            title="Active cursor handoff",
            description="Keeps the agent serialized.",
            status=TaskStatus.waiting_approval,
            assigned_agent_id=agent_id,
            created_at=now,
            updated_at=now,
            last_run_id=blocker_run_id,
            correlation_id=new_id("corr"),
        )
    )
    runs_repo.upsert(
        Run(
            run_id=blocker_run_id,
            task_id=blocker_task_id,
            agent_id=agent_id,
            status="running",
            queued_at=now,
            started_at=now,
            output_snapshot={"status": "pending_handoff"},
        )
    )
    tasks_repo.upsert(
        Task(
            task_id=stale_task_id,
            title="Stale cursor pending run",
            description="Should not remain queued forever behind a handoff.",
            status=TaskStatus.queued,
            assigned_agent_id=agent_id,
            created_at=old,
            updated_at=old,
            last_run_id=stale_run_id,
            correlation_id=new_id("corr"),
        )
    )
    stale_run = Run(
        run_id=stale_run_id,
        task_id=stale_task_id,
        agent_id=agent_id,
        status="pending",
        queued_at=old,
    )
    runs_repo.upsert(stale_run)
    ensure_base_run_steps(stale_run)

    _expire_stale_pending_runs()

    stale_task = tasks_repo.get(stale_task_id)
    stale_run_after = runs_repo.get(stale_run_id)
    blocker_task = tasks_repo.get(blocker_task_id)
    steps, _total = list_steps_for_run(stale_run_id)

    assert stale_task is not None
    assert stale_task.status == TaskStatus.failed
    assert stale_task.last_error == "queue_timeout"
    assert stale_run_after is not None
    assert stale_run_after.status == "failed"
    assert blocker_task is not None
    assert blocker_task.status == TaskStatus.waiting_approval
    assert {step.step_type: step.status for step in steps} == {
        "plan": "succeeded",
        "execute": "failed",
        "summarize": "succeeded",
    }

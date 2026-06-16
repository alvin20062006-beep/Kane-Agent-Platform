from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..models import WatchdogEvent, WatchdogStatus, WatchdogSummary
from ..version import PLATFORM_VERSION
from ..settings_env import get_api_public_url, get_local_bridge_url, get_stalled_task_minutes
from ..store.repositories import (
    agents_repo,
    conversations_repo,
    local_bridge_repo,
    master_tasks_repo,
    notification_deliveries_repo,
    runs_repo,
    task_events_repo,
    tasks_repo,
    watchdog_events_repo,
)
from .worker_queue import get_worker_state


def _parse_iso(ts: str) -> datetime:
    # Handle ...+00:00
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _latest_watchdog_issue_state(events: list[WatchdogEvent]) -> list[WatchdogEvent]:
    latest: dict[tuple[str | None, str | None, str | None], WatchdogEvent] = {}
    for event in events:
        key = (event.task_id, event.issue_class, event.normalized_issue_signature)
        existing = latest.get(key)
        if existing is None or existing.created_at < event.created_at:
            latest[key] = event
    return list(latest.values())


def build_watchdog_status() -> WatchdogStatus:
    tasks = tasks_repo.list()
    agents = agents_repo.list()
    runs = runs_repo.list()
    conversations = conversations_repo.list()
    bridge_agents = local_bridge_repo.list()
    persisted_events = watchdog_events_repo.list()

    now = datetime.now(tz=timezone.utc)
    stalled_threshold = now - timedelta(minutes=get_stalled_task_minutes())

    running_tasks = sum(1 for t in tasks if t.status.value == "running")
    stalled_tasks = 0
    for t in tasks:
        if t.status.value != "running":
            continue
        try:
            if t.updated_at and _parse_iso(t.updated_at) < stalled_threshold:
                stalled_tasks += 1
        except Exception:  # noqa: BLE001
            stalled_tasks += 1

    failed_recent = 0
    day_ago = now - timedelta(hours=24)
    for r in runs:
        if r.status != "failed":
            continue
        try:
            if r.finished_at and _parse_iso(r.finished_at) > day_ago:
                failed_recent += 1
        except Exception:  # noqa: BLE001
            failed_recent += 1

    stalled_agents = sum(1 for a in agents if a.status.value == "stalled")
    offline_agents = sum(1 for a in agents if a.status.value == "offline")
    degraded_agents = sum(1 for a in agents if a.status.value == "degraded")
    waiting_handoffs = sum(1 for t in tasks if t.status.value == "waiting_approval")

    bridge_reachable: bool | None = None
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{get_local_bridge_url()}/health")
            bridge_reachable = r.status_code == 200
    except Exception:  # noqa: BLE001
            bridge_reachable = False

    last_run_finished_at = None
    finished = [r.finished_at for r in runs if r.finished_at]
    if finished:
        last_run_finished_at = max(finished)

    last_agent_heartbeat_at = None
    heartbeats = [a.last_heartbeat_at for a in agents if a.last_heartbeat_at]
    bridge_seen = [a.last_seen_at for a in bridge_agents if a.last_seen_at]
    all_seen = [*heartbeats, *bridge_seen]
    if all_seen:
        last_agent_heartbeat_at = max(all_seen)

    latest_issue_state = _latest_watchdog_issue_state(persisted_events)

    summary = WatchdogSummary(
        running_tasks=running_tasks,
        stalled_tasks=stalled_tasks,
        failed_tasks_recent=failed_recent,
        stalled_agents=stalled_agents,
        offline_agents=offline_agents,
        degraded_agents=degraded_agents,
        bridge_reachable=bridge_reachable,
        waiting_handoffs=waiting_handoffs,
        open_issues=sum(1 for event in latest_issue_state if event.issue_status == "open"),
        escalated_issues=sum(1 for event in latest_issue_state if event.issue_status == "escalated"),
        last_run_finished_at=last_run_finished_at,
        last_agent_heartbeat_at=last_agent_heartbeat_at,
    )

    events: list[WatchdogEvent] = sorted(
        persisted_events,
        key=lambda item: item.created_at,
        reverse=True,
    )[:8]
    if stalled_tasks:
        events.append(
            WatchdogEvent(
                event_id="wd_stalled_tasks",
                type="stalled_tasks",
                message=f"{stalled_tasks} task(s) running without recent updates (>{get_stalled_task_minutes()}m)",
                created_at=now.isoformat(),
                severity="warn",
                recovery_hint="Check /tasks/{id}/timeline and rerun or mark failed if the executor is stuck.",
            )
        )
    if bridge_reachable is False:
        events.append(
            WatchdogEvent(
                event_id="wd_bridge_down",
                type="bridge_unreachable",
                message="Local Bridge health check failed (external agent execution may not work)",
                created_at=now.isoformat(),
                severity="error",
                recovery_hint="Start apps/local-bridge and re-run the external task or submit the result manually.",
            )
        )
    if waiting_handoffs:
        events.append(
            WatchdogEvent(
                event_id="wd_waiting_handoffs",
                type="waiting_external_result",
                message=f"{waiting_handoffs} task(s) are waiting for external bridge completion",
                created_at=now.isoformat(),
                severity="warn",
                recovery_hint="Submit POST /local-bridge/result or /integrations/bridge/complete when the external agent finishes.",
            )
        )

    recovery_hints = []
    if bridge_reachable is False:
        recovery_hints.append("Local Bridge is unreachable; start it before running Claude Code, Cursor, or OpenClaw tasks.")
    if failed_recent:
        recovery_hints.append("Recent failed runs exist; inspect /runs and use retry + rerun after checking the last error.")
    if waiting_handoffs:
        recovery_hints.append("Some tasks are waiting for external completion; post bridge results back to Octopus to unblock them.")
    if not recovery_hints:
        recovery_hints.append("No active recovery action is required right now.")

    latest_issues = sorted(
        latest_issue_state,
        key=lambda item: item.last_seen_at or item.created_at,
        reverse=True,
    )[:24]

    return WatchdogStatus(
        summary=summary,
        events=events[:12],
        recovery_hints=recovery_hints,
        latest_issues=latest_issues,
    )


def probe_local_bridge_detailed() -> dict[str, Any]:
    """
    Fresh HTTP probe used by the control-plane wizard (POST /local-bridge/probe).
    """
    url = get_local_bridge_url()
    reachable: bool | None = None
    error: str | None = None
    health_body: Any = None
    status_body: Any = None
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{url}/health")
            reachable = r.status_code == 200
            if reachable:
                try:
                    health_body = r.json()
                except Exception:
                    health_body = None
            try:
                s = c.get(f"{url}/v1/status")
                if s.status_code == 200:
                    status_body = s.json()
            except Exception:
                status_body = None
    except Exception as e:  # noqa: BLE001
        reachable = False
        error = str(e)

    hints: list[str] = []
    if not reachable:
        hints.append(
            "在本机启动 Local Bridge：cd apps/local-bridge && .venv\\Scripts\\activate && "
            "python -m uvicorn app.main:app --host 127.0.0.1 --port 8010"
        )
        hints.append("确认 API 进程的环境变量 OCTOPUS_LOCAL_BRIDGE_URL 指向该 Bridge（默认 http://127.0.0.1:8010）。")
        hints.append("确认 Web 的 NEXT_PUBLIC_API_BASE_URL 指向当前 Octopus API，避免连到旧实例。")
    else:
        hints.append("Bridge 可达。外部 Agent 任务仍可能因 handoff/OpenClaw URL/CLI 缺失而等待或失败——查看任务详情与 /integrations/bridge/complete 说明。")

    merged_bs: dict[str, Any] = {}
    if isinstance(status_body, dict):
        merged_bs.update(status_body)
    if isinstance(health_body, dict):
        for key in (
            "claude_on_path",
            "codex_on_path",
            "cursor_on_path",
            "openclaw_configured",
            "supported_adapters",
            "bridge_version",
        ):
            if key in health_body:
                merged_bs.setdefault(key, health_body[key])

    return {
        "url": url,
        "api_public_url": get_api_public_url(),
        "reachable": reachable,
        "error": error,
        "health": health_body,
        "bridge_status": merged_bs if merged_bs else status_body,
        "hints": hints,
        "probed_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def build_metrics() -> dict:
    tasks = tasks_repo.list()
    agents = agents_repo.list()
    runs = runs_repo.list()
    conversations = conversations_repo.list()
    bridge_agents = local_bridge_repo.list()
    by_status: dict[str, int] = {}
    for t in tasks:
        by_status[t.status.value] = by_status.get(t.status.value, 0) + 1

    failed_runs = sum(1 for r in runs if r.status == "failed")
    ok_runs = sum(1 for r in runs if r.status == "succeeded")
    queued_runs = sum(1 for r in runs if r.status == "pending")
    queued_by_priority = {"urgent": 0, "high": 0, "normal": 0, "low": 0}
    for task in tasks:
        if task.status.value == "queued":
            queued_by_priority[task.queue_priority] = queued_by_priority.get(task.queue_priority, 0) + 1
    waiting_handoffs = sum(1 for t in tasks if t.status.value == "waiting_approval")
    last_run = max((r.finished_at or r.started_at or r.queued_at for r in runs), default=None)

    bridge = {"reachable": None, "url": get_local_bridge_url()}
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{get_local_bridge_url()}/health")
            bridge["reachable"] = r.status_code == 200
    except Exception:  # noqa: BLE001
        bridge["reachable"] = False

    agent_by: dict[str, int] = {}
    for a in agents:
        agent_by[a.status.value] = agent_by.get(a.status.value, 0) + 1

    watchdog_events = _latest_watchdog_issue_state(watchdog_events_repo.list())
    watchdog_open = sum(1 for event in watchdog_events if event.issue_status == "open")
    watchdog_escalated = sum(1 for event in watchdog_events if event.issue_status == "escalated")
    watchdog_resolved = sum(1 for event in watchdog_events if event.issue_status == "resolved")
    _orch_terminal = {"completed", "failed", "cancelled"}
    active_orchestrators = sum(
        1 for m in master_tasks_repo.list() if m.status not in _orch_terminal
    )

    return {
        "version": PLATFORM_VERSION,
        "tasks": {"total": len(tasks), "by_status": by_status},
        "conversations": {"total": len(conversations)},
        "runs": {
            "total": len(runs),
            "succeeded": ok_runs,
            "failed": failed_runs,
            "queued": queued_runs,
            "last_finished_or_started_at": last_run,
        },
        "agents": {"total": len(agents), "by_status": agent_by},
        "local_bridge": {
            **bridge,
            "registered_agents": len(bridge_agents),
            "last_seen_at": max((a.last_seen_at for a in bridge_agents), default=None),
        },
        "fault_recovery": {
            "waiting_handoffs": waiting_handoffs,
            "recent_failed_runs": failed_runs,
            "retry_supported": True,
            "open_issues": watchdog_open,
            "escalated_issues": watchdog_escalated,
            "resolved_issues": watchdog_resolved,
        },
        "worker": {
            **get_worker_state(),
            "queued_runs": queued_runs,
            "queued_by_priority": queued_by_priority,
        },
        "notifications": {
            "deliveries_total": len(notification_deliveries_repo.list()),
            "deliveries_failed_recent": sum(1 for d in notification_deliveries_repo.list()[-50:] if d.status == "failed"),
        },
        "orchestrator": {"active_masters": active_orchestrators},
    }


def build_local_bridge_recent_callback_audit(*, limit: int = 12) -> list[dict[str, Any]]:
    tasks_by_id = {task.task_id: task for task in tasks_repo.list()}
    runs_by_id = {run.run_id: run for run in runs_repo.list()}
    items: list[dict[str, Any]] = []

    for run in runs_repo.list():
        callback_summary = run.callback_summary or {}
        if not callback_summary:
            continue
        task = tasks_by_id.get(run.task_id)
        items.append(
            {
                "kind": "accepted",
                "created_at": callback_summary.get("received_at") or run.finished_at or run.started_at or run.queued_at,
                "task_id": run.task_id,
                "run_id": run.run_id,
                "agent_id": run.agent_id or (task.assigned_agent_id if task else None),
                "integration_path": callback_summary.get("integration_path") or run.integration_path,
                "status": callback_summary.get("status") or run.status,
                "message": "Accepted bridge callback",
                "source": "callback_summary",
                "correlation_id": run.correlation_id or (task.correlation_id if task else None),
            }
        )

    for event in task_events_repo.list():
        if event.type not in {"callback_rejected", "duplicate_callback", "late_callback"}:
            continue
        task = tasks_by_id.get(event.task_id)
        run = runs_by_id.get((event.payload or {}).get("run_id", "")) if event.payload else None
        kind = (
            "rejected"
            if event.type == "callback_rejected"
            else "duplicate"
            if event.type == "duplicate_callback"
            else "late"
        )
        items.append(
            {
                "kind": kind,
                "created_at": event.created_at,
                "task_id": event.task_id,
                "run_id": (event.payload or {}).get("run_id"),
                "agent_id": run.agent_id if run else (task.assigned_agent_id if task else None),
                "integration_path": (event.payload or {}).get("integration_path"),
                "status": (event.payload or {}).get("status") or kind,
                "message": event.message,
                "source": "task_event",
                "correlation_id": event.correlation_id or (run.correlation_id if run else None),
            }
        )

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]

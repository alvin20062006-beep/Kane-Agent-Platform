from __future__ import annotations

from collections import defaultdict

from ..models import ObserverPacket, ObserverPattern, ObserverSummary
from ..store.repositories import runs_repo, tasks_repo, watchdog_events_repo
from .runtime_audit import now_iso


def build_observer_summary(*, limit: int = 12) -> ObserverSummary:
    tasks = {task.task_id: task for task in tasks_repo.list()}
    runs = sorted(
        runs_repo.list(),
        key=lambda item: item.finished_at or item.started_at or item.queued_at or "",
        reverse=True,
    )
    watchdog_events = sorted(watchdog_events_repo.list(), key=lambda item: item.created_at, reverse=True)

    latest_issue_by_run: dict[str, tuple[str | None, str | None]] = {}
    latest_recovery_by_task: dict[str, str | None] = {}
    for event in watchdog_events:
        if event.related_run_id and event.related_run_id not in latest_issue_by_run:
            latest_issue_by_run[event.related_run_id] = (event.issue_class, event.issue_status)
        if event.task_id and event.task_id not in latest_recovery_by_task:
            latest_recovery_by_task[event.task_id] = event.issue_status

    packets: list[ObserverPacket] = []
    failure_rollup: dict[str, list[str | None]] = defaultdict(list)
    success_rollup: dict[str, list[str | None]] = defaultdict(list)
    recovery_rollup: dict[str, list[str | None]] = defaultdict(list)

    for run in runs[: max(limit * 2, 24)]:
        task = tasks.get(run.task_id)
        if not task:
            continue
        issue_class, issue_status = latest_issue_by_run.get(run.run_id, (None, None))
        time_basis = (
            "finished_at"
            if run.finished_at
            else "started_at"
            if run.started_at
            else "queued_at"
            if run.queued_at
            else "task_updated_at"
            if task.updated_at
            else "task_created_at"
        )
        packet = ObserverPacket(
            packet_id=f"pkt_{run.run_id}",
            task_id=task.task_id,
            run_id=run.run_id,
            correlation_id=run.correlation_id or task.correlation_id,
            agent_id=run.agent_id or task.assigned_agent_id,
            status=run.status,
            execution_mode=task.execution_mode,
            queue_priority=task.queue_priority,
            integration_path=run.integration_path,
            error=run.error or task.last_error,
            summary=task.result_summary or run.output_excerpt,
            issue_class=issue_class,
            recovery_state=issue_status or latest_recovery_by_task.get(task.task_id),
            created_at=run.finished_at or run.started_at or run.queued_at or task.updated_at or task.created_at,
            time_basis=time_basis,
        )
        packets.append(packet)

        if run.status == "failed":
            key = issue_class or run.error or "failed_run"
            failure_rollup[key].append(packet.agent_id)
        elif run.status == "succeeded":
            key = f"{packet.agent_id or 'unassigned'}:{packet.integration_path or 'builtin'}"
            success_rollup[key].append(packet.agent_id)

    for event in watchdog_events[: max(limit * 3, 24)]:
        if event.suggested_action or event.issue_status:
            key = f"{event.issue_class or event.type}:{event.issue_status or 'open'}"
            recovery_rollup[key].append(event.agent_id)

    def _patterns(source: dict[str, list[str | None]], *, packets_for_key: dict[str, str | None] | None = None) -> list[ObserverPattern]:
        items: list[ObserverPattern] = []
        for key, agent_ids in source.items():
            items.append(
                ObserverPattern(
                    key=key,
                    count=len(agent_ids),
                    latest_at=packets_for_key.get(key) if packets_for_key else None,
                    summary=key,
                    related_agent_id=next((agent_id for agent_id in reversed(agent_ids) if agent_id), None),
                )
            )
        items.sort(key=lambda item: (-item.count, item.key))
        return items[:limit]

    failure_latest = {
        (packet.issue_class or packet.error or "failed_run"): packet.created_at
        for packet in packets
        if packet.status == "failed"
    }
    success_latest = {
        f"{packet.agent_id or 'unassigned'}:{packet.integration_path or 'builtin'}": packet.created_at
        for packet in packets
        if packet.status == "succeeded"
    }
    recovery_latest = {
        f"{event.issue_class or event.type}:{event.issue_status or 'open'}": event.created_at
        for event in watchdog_events
    }

    return ObserverSummary(
        generated_at=now_iso(),
        recent_packets=packets[:limit],
        failure_patterns=_patterns(failure_rollup, packets_for_key=failure_latest),
        success_patterns=_patterns(success_rollup, packets_for_key=success_latest),
        recovery_patterns=_patterns(recovery_rollup, packets_for_key=recovery_latest),
        totals={
            "tasks": len(tasks),
            "runs": len(runs),
            "failed_runs": sum(1 for run in runs if run.status == "failed"),
            "succeeded_runs": sum(1 for run in runs if run.status == "succeeded"),
            "watchdog_events": len(watchdog_events),
        },
    )

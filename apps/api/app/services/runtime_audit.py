from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..id_utils import new_id
from ..models import Agent, ProcessedActionReceipt, Run, Task, TaskEventRecord, WatchdogEvent
from ..store.repositories import processed_action_receipts_repo, runs_repo, task_events_repo, tasks_repo, watchdog_events_repo


APP_VERSION = "1.1.0"
DEFAULT_RECEIPT_CLAIM_TTL_SECONDS = 30


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def ensure_task_correlation(task: Task) -> Task:
    if task.correlation_id:
        return task
    updated = task.model_copy(update={"correlation_id": new_id("corr")})
    tasks_repo.upsert(updated)
    return updated


def build_run_input_snapshot(task: Task) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "execution_mode": task.execution_mode,
        "queue_priority": task.queue_priority,
        "assigned_agent_id": task.assigned_agent_id,
        "retry_count": task.retry_count,
        "source_task_id": task.source_task_id,
    }


def resolve_parent_run_id(task: Task) -> str | None:
    if not task.last_run_id:
        return None
    parent_run = runs_repo.get(task.last_run_id)
    if not parent_run:
        return None
    if parent_run.task_id != task.task_id:
        return None
    return parent_run.run_id


def build_environment_summary(
    task: Task,
    agent: Agent,
    *,
    integration_path: str | None = None,
    bridge_version: str | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent.agent_id,
        "adapter_id": agent.adapter_id,
        "execution_mode": task.execution_mode,
        "integration_path": integration_path,
        "app_version": APP_VERSION,
        "bridge_version": bridge_version,
        "build_id": "dev",
    }


def normalize_issue(raw_error: str | None, fallback_issue_class: str) -> tuple[str, str]:
    text = (raw_error or fallback_issue_class or "unknown").strip().lower()
    if not text:
        return ("unknown", "unknown")
    replacements = [
        ("http://127.0.0.1:8010", "{bridge_url}"),
        ("http://localhost:8010", "{bridge_url}"),
    ]
    signature = text
    for src, dst in replacements:
        signature = signature.replace(src, dst)
    issue_class = fallback_issue_class
    if "queue_timeout" in text:
        issue_class = "task_worker_stalled"
    elif "callback" in text:
        issue_class = "external_callback_missing"
    elif "bridge" in text or "local_bridge" in text:
        issue_class = "bridge_timeout"
    elif "agent" in text and "not_found" in text:
        issue_class = "agent_unreachable"
    return issue_class, signature[:400]


def append_task_event(
    task_id: str,
    event_type: str,
    message: str | None,
    *,
    correlation_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> TaskEventRecord:
    event = TaskEventRecord(
        event_id=new_id("evt"),
        task_id=task_id,
        type=event_type,
        message=message,
        payload=payload,
        created_at=now_iso(),
        correlation_id=correlation_id,
    )
    task_events_repo.upsert(event)
    return event


def mark_task_attention(task: Task, reason: str, *, source: str) -> Task:
    updated = task.model_copy(
        update={
            "needs_attention": True,
            "attention_reason": reason,
            "updated_at": now_iso(),
        }
    )
    tasks_repo.upsert(updated)
    append_task_event(
        task.task_id,
        "task_needs_attention",
        reason,
        correlation_id=task.correlation_id,
        payload={
            "reason": reason,
            "source": source,
            "correlation_id": task.correlation_id,
        },
    )
    return updated


def append_watchdog_issue(
    issue_type: str,
    message: str,
    *,
    severity: str = "warn",
    task: Task | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    raw_error: str | None = None,
    suggested_action: str | None = None,
    source: str = "watchdog",
    issue_status: str = "open",
    recovery_hint: str | None = None,
    parent_run_id: str | None = None,
    event_id: str | None = None,
    created_at: str | None = None,
    first_seen_at: str | None = None,
    last_seen_at: str | None = None,
    occurrence_count: int = 1,
) -> WatchdogEvent:
    ts = created_at or now_iso()
    issue_class, signature = normalize_issue(raw_error or message, issue_type)
    event = WatchdogEvent(
        event_id=event_id or new_id("wd"),
        type=issue_type,
        message=message,
        created_at=ts,
        first_seen_at=first_seen_at or ts,
        last_seen_at=last_seen_at or ts,
        occurrence_count=occurrence_count,
        severity=severity,  # type: ignore[arg-type]
        task_id=task.task_id if task else None,
        agent_id=(agent_id or task.assigned_agent_id) if task else agent_id,
        recovery_hint=recovery_hint,
        correlation_id=task.correlation_id if task else None,
        source=source,  # type: ignore[arg-type]
        issue_status=issue_status,  # type: ignore[arg-type]
        suggested_action=suggested_action,
        raw_error=raw_error,
        normalized_issue_signature=signature,
        issue_class=issue_class,
        related_run_id=run_id,
        parent_run_id=parent_run_id,
    )
    watchdog_events_repo.upsert(event)
    return event


def _audit_stale_receipt(existing: ProcessedActionReceipt, *, action_type: str, key: str) -> None:
    message = f"Stale claimed receipt detected for {action_type}"
    payload = {
        "action_type": action_type,
        "receipt_key": key,
        "receipt_id": existing.receipt_id,
        "previous_claimed_at": existing.claimed_at,
        "claim_ttl_seconds": existing.claim_ttl_seconds,
        "previous_status": existing.status,
    }
    if existing.task_id:
        append_task_event(
            existing.task_id,
            "stale_claimed_receipt",
            message,
            correlation_id=existing.correlation_id,
            payload=payload,
        )
    else:
        append_watchdog_issue(
            "stale_claimed_receipt",
            message,
            severity="warn",
            agent_id=None,
            raw_error="stale_claimed_receipt",
            suggested_action="reclaim_receipt",
            source="watchdog",
            issue_status="resolved",
            recovery_hint="Receipt claim TTL expired and the request was reclaimed conservatively.",
        )


def _is_receipt_stale(existing: ProcessedActionReceipt) -> bool:
    if existing.status != "claimed":
        return False
    claim_ts = _parse_iso(existing.claimed_at or existing.updated_at or existing.created_at)
    if claim_ts is None:
        return False
    ttl_seconds = max(existing.claim_ttl_seconds or DEFAULT_RECEIPT_CLAIM_TTL_SECONDS, 1)
    return datetime.now(tz=timezone.utc) >= claim_ts + timedelta(seconds=ttl_seconds)


def make_receipt_key(action_type: str, *parts: str | None) -> str:
    joined = ":".join((part or "_") for part in parts)
    return f"{action_type}:{joined}"


def get_processed_receipt(action_type: str, key: str) -> ProcessedActionReceipt | None:
    receipt_id = f"{action_type}:{key}"
    return processed_action_receipts_repo.get(receipt_id)


def claim_processed_receipt(
    action_type: str,
    key: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    correlation_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[bool, ProcessedActionReceipt]:
    receipt_id = f"{action_type}:{key}"
    existing = processed_action_receipts_repo.get(receipt_id)
    claimed_at = now_iso()
    receipt = ProcessedActionReceipt(
        receipt_id=receipt_id,
        action_type=action_type,  # type: ignore[arg-type]
        key=key,
        task_id=task_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="claimed",
        result_ref=None,
        payload=payload,
        created_at=existing.created_at if existing else claimed_at,
        claimed_at=claimed_at,
        claim_ttl_seconds=existing.claim_ttl_seconds if existing else DEFAULT_RECEIPT_CLAIM_TTL_SECONDS,
        updated_at=claimed_at,
    )
    if not existing:
        created = processed_action_receipts_repo.create_if_absent(receipt)
        if created:
            return True, receipt
        return False, processed_action_receipts_repo.get(receipt_id) or receipt

    if existing.status == "failed":
        reclaimed = processed_action_receipts_repo.compare_and_swap(
            receipt,
            {"status": "failed", "updated_at": existing.updated_at},
        )
        if reclaimed:
            return True, receipt
        return False, processed_action_receipts_repo.get(receipt_id) or existing

    if _is_receipt_stale(existing):
        _audit_stale_receipt(existing, action_type=action_type, key=key)
        reclaimed = processed_action_receipts_repo.compare_and_swap(
            receipt,
            {"status": "claimed", "updated_at": existing.updated_at},
        )
        if reclaimed:
            return True, receipt
        return False, processed_action_receipts_repo.get(receipt_id) or existing

    return False, existing


def finalize_processed_receipt(
    action_type: str,
    key: str,
    *,
    status: str,
    task_id: str | None = None,
    run_id: str | None = None,
    correlation_id: str | None = None,
    result_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ProcessedActionReceipt:
    receipt_id = f"{action_type}:{key}"
    existing = processed_action_receipts_repo.get(receipt_id)
    ts = now_iso()
    receipt = ProcessedActionReceipt(
        receipt_id=receipt_id,
        action_type=action_type,  # type: ignore[arg-type]
        key=key,
        task_id=task_id if task_id is not None else existing.task_id if existing else None,
        run_id=run_id if run_id is not None else existing.run_id if existing else None,
        correlation_id=correlation_id if correlation_id is not None else existing.correlation_id if existing else None,
        status=status,  # type: ignore[arg-type]
        result_ref=result_ref if result_ref is not None else existing.result_ref if existing else None,
        payload=payload if payload is not None else existing.payload if existing else None,
        created_at=existing.created_at if existing else ts,
        claimed_at=existing.claimed_at if existing else None,
        claim_ttl_seconds=existing.claim_ttl_seconds if existing else DEFAULT_RECEIPT_CLAIM_TTL_SECONDS,
        updated_at=ts,
    )
    processed_action_receipts_repo.upsert(receipt)
    return receipt


def create_receipt(
    action_type: str,
    key: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    correlation_id: str | None = None,
    status: str = "completed",
    result_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ProcessedActionReceipt:
    return finalize_processed_receipt(
        action_type,
        key,
        status=status,
        task_id=task_id,
        run_id=run_id,
        correlation_id=correlation_id,
        result_ref=result_ref,
        payload=payload,
    )

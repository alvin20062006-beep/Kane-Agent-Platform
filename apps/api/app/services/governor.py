"""P3 Governor Layer.

Pipeline: suggestion → build_action → gate_evaluation → decision → (confirm) → execute → receipt → audit

Allowlist (immutable):
  retry_run | acknowledge_escalation | resolve_escalation | adjust_queue_priority

Kill switches:
  GOVERNOR_ENABLED              (default on)
  GOVERNOR_AUTO_EXECUTE_ENABLED (default OFF — require human confirm)

Circuit breaker: process-local; resets on restart.  Purely a safety mechanism.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import (
    EscalationActionBody,
    ExecutionReceipt,
    GovernableAction,
    GovernorDecision,
    _GOVERNOR_ALLOWLIST,
)
from ..settings_env import get_governor_auto_execute_enabled, get_governor_enabled
from ..store.repositories import (
    advisor_suggestions_repo,
    governable_actions_repo,
    governor_decisions_repo,
    governor_receipts_repo,
    tasks_repo,
)
from .runtime_audit import append_task_event, append_watchdog_issue, now_iso

# ── Circuit breaker (process-local, resets on restart) ───────────────────────

_circuit_failures: dict[str, int] = {}   # action_type:target_id → consecutive failures
_CIRCUIT_BREAKER_THRESHOLD = 3


def _circuit_ok(action: GovernableAction) -> bool:
    key = f"{action.action_type}:{action.target_id}"
    return _circuit_failures.get(key, 0) < _CIRCUIT_BREAKER_THRESHOLD


def _circuit_record_failure(action: GovernableAction) -> None:
    key = f"{action.action_type}:{action.target_id}"
    _circuit_failures[key] = _circuit_failures.get(key, 0) + 1


def _circuit_record_success(action: GovernableAction) -> None:
    key = f"{action.action_type}:{action.target_id}"
    _circuit_failures.pop(key, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_idempotency_key(action_type: str, target_id: str, decision_id: str) -> str:
    raw = f"{action_type}:{target_id}:{decision_id}"
    return f"gov_{hashlib.sha1(raw.encode()).hexdigest()[:16]}"  # noqa: S324


def _find_duplicate_receipt(idempotency_key: str) -> ExecutionReceipt | None:
    for receipt in governor_receipts_repo.list():
        if receipt.idempotency_key == idempotency_key:
            return receipt
    return None


def _compute_risk(
    action_type: str,
    target_id: str,
    parameters: dict[str, Any],
) -> str:
    """Compute risk level without side effects."""
    if action_type == "retry_run":
        task = tasks_repo.get(target_id)
        retry_count = task.retry_count if task else 0
        if retry_count == 0:
            return "low"
        if retry_count == 1:
            return "medium"
        return "high"
    if action_type == "acknowledge_escalation":
        return "low"
    if action_type == "resolve_escalation":
        return "medium"
    if action_type == "adjust_queue_priority":
        return "low"
    return "high"


def _recovery_at_ceiling(target_id: str, action_type: str) -> bool:
    """True when a task has exhausted its recovery budget."""
    if action_type != "retry_run":
        return False
    task = tasks_repo.get(target_id)
    if not task:
        return False
    max_attempts = getattr(task, "max_recovery_attempts", None) or 3
    count = getattr(task, "recovery_attempt_count", None) or 0
    return count >= max_attempts


# ── Gate evaluation ───────────────────────────────────────────────────────────

def _evaluate_gates(
    action: GovernableAction,
) -> tuple[list[str], list[str], str]:
    """
    Returns (gates_passed, gates_failed, denial_reason).
    gates_failed non-empty → decision = "deny".
    """
    passed: list[str] = []
    failed: list[str] = []
    reason = ""

    # Gate 1: kill switch
    if not get_governor_enabled():
        failed.append("policy_gate")
        return passed, failed, "Governor is disabled (GOVERNOR_ENABLED=0)"
    passed.append("policy_gate")

    # Gate 2: allowlist
    if action.action_type not in _GOVERNOR_ALLOWLIST:
        failed.append("allowlist_gate")
        return passed, failed, f"Action type '{action.action_type}' is not in the allowlist"
    passed.append("allowlist_gate")

    # Gate 3: risk gate (high risk → deny)
    if action.risk_level == "high":
        failed.append("risk_gate")
        return passed, failed, f"Risk level 'high' is above the execution threshold"
    passed.append("risk_gate")

    # Gate 4: recovery ceiling
    if _recovery_at_ceiling(action.target_id, action.action_type):
        failed.append("recovery_gate")
        return passed, failed, "Task has reached its recovery attempt ceiling"
    passed.append("recovery_gate")

    # Gate 5: circuit breaker
    if not _circuit_ok(action):
        failed.append("circuit_breaker_gate")
        return passed, failed, (
            f"Circuit breaker open: {_CIRCUIT_BREAKER_THRESHOLD} consecutive failures "
            f"for {action.action_type}:{action.target_id}"
        )
    passed.append("circuit_breaker_gate")

    return passed, failed, reason


def _choose_decision(
    risk_level: str,
    gates_failed: list[str],
) -> str:
    if gates_failed:
        return "deny"
    # High risk is already caught by the risk gate, but guard defensively
    if risk_level == "high":
        return "deny"
    if risk_level == "low" and get_governor_auto_execute_enabled():
        return "auto_execute"
    return "require_confirmation"


# ── Action execution ──────────────────────────────────────────────────────────

def _do_retry_run(action: GovernableAction) -> str:
    from .task_lifecycle import retry_task  # local import to avoid circular
    task = retry_task(action.target_id)
    return f"Task '{action.target_id}' retried; status={task.status.value} retry_count={task.retry_count}"


def _do_acknowledge_escalation(action: GovernableAction) -> str:
    from .escalations import update_escalation
    note = action.parameters.get("note", "Governor-initiated acknowledgement")
    event = update_escalation(action.target_id, "processing", EscalationActionBody(note=note))
    return f"Escalation '{action.target_id}' acknowledged; new event={event.event_id}"


def _do_resolve_escalation(action: GovernableAction) -> str:
    from .escalations import update_escalation
    note = action.parameters.get("note", "Governor-initiated resolution")
    event = update_escalation(action.target_id, "resolved", EscalationActionBody(note=note))
    return f"Escalation '{action.target_id}' resolved; new event={event.event_id}"


def _do_adjust_queue_priority(action: GovernableAction) -> str:
    new_priority = action.parameters.get("priority", "high")
    valid = {"low", "normal", "high", "urgent"}
    if new_priority not in valid:
        raise ValueError(f"Invalid priority '{new_priority}'; must be one of {valid}")
    task = tasks_repo.get(action.target_id)
    if not task:
        raise ValueError(f"Task '{action.target_id}' not found")
    tasks_repo.upsert(
        task.model_copy(update={"queue_priority": new_priority, "updated_at": now_iso()})
    )
    append_task_event(
        action.target_id,
        "queue_priority_adjusted",
        f"Queue priority adjusted to '{new_priority}' by Governor",
        correlation_id=action.correlation_id,
        payload={
            "previous_priority": task.queue_priority,
            "new_priority": new_priority,
            "action_id": action.action_id,
            "source": "governor",
        },
    )
    return f"Task '{action.target_id}' queue_priority set to '{new_priority}'"


_EXECUTORS = {
    "retry_run": _do_retry_run,
    "acknowledge_escalation": _do_acknowledge_escalation,
    "resolve_escalation": _do_resolve_escalation,
    "adjust_queue_priority": _do_adjust_queue_priority,
}


def _run_action(action: GovernableAction, decision: GovernorDecision) -> ExecutionReceipt:
    """Execute the action, write audit, return immutable receipt."""
    idempotency_key = _make_idempotency_key(
        action.action_type, action.target_id, decision.decision_id
    )
    # Idempotency check
    existing = _find_duplicate_receipt(idempotency_key)
    if existing:
        return existing

    ts = now_iso()
    executor = _EXECUTORS.get(action.action_type)
    outcome: str
    error: str | None = None
    result_summary: str | None = None

    try:
        if executor is None:
            raise ValueError(f"No executor for action_type '{action.action_type}'")
        result_summary = executor(action)
        outcome = "succeeded"
        _circuit_record_success(action)
    except Exception as exc:  # noqa: BLE001
        outcome = "failed"
        error = str(exc)
        _circuit_record_failure(action)

    receipt = ExecutionReceipt(
        receipt_id=new_id("grc"),
        decision_id=decision.decision_id,
        action_id=action.action_id,
        suggestion_id=action.suggestion_id,
        action_type=action.action_type,
        target_id=action.target_id,
        outcome=outcome,  # type: ignore[arg-type]
        error=error,
        result_summary=result_summary,
        executed_at=ts,
        idempotency_key=idempotency_key,
        correlation_id=action.correlation_id,
    )
    governor_receipts_repo.upsert(receipt)

    # Audit events
    if outcome == "succeeded":
        _audit(
            "governor_action_executed",
            result_summary or f"Governor executed {action.action_type}",
            decision=decision,
            action=action,
        )
    else:
        _audit(
            "governor_action_failed",
            f"Governor action failed: {error}",
            decision=decision,
            action=action,
        )

    return receipt


# ── Audit helpers ─────────────────────────────────────────────────────────────

def _audit(
    event_type: str,
    message: str,
    *,
    decision: GovernorDecision,
    action: GovernorDecision | GovernableAction | None = None,
) -> None:
    payload: dict[str, Any] = {
        "decision_id": decision.decision_id,
        "decision": decision.decision,
        "risk_level": decision.risk_level,
        "gates_passed": decision.gates_passed,
        "gates_failed": decision.gates_failed,
        "policy_snapshot": decision.policy_snapshot,
    }
    if action and isinstance(action, GovernableAction):
        payload["action_id"] = action.action_id
        payload["action_type"] = action.action_type
        payload["target_id"] = action.target_id

    if decision.source_task_id:
        append_task_event(
            decision.source_task_id,
            event_type,
            message,
            correlation_id=decision.correlation_id,
            payload=payload,
        )
    else:
        # Fall back to watchdog audit stream
        from ..store.repositories import watchdog_events_repo  # noqa: PLC0415
        from ..models import WatchdogEvent  # noqa: PLC0415
        evt = WatchdogEvent(
            event_id=new_id("wd"),
            type=event_type,
            message=message,
            created_at=now_iso(),
            severity="info",
            task_id=decision.source_task_id,
            correlation_id=decision.correlation_id,
            issue_status="resolved",
            source="governor",
        )
        watchdog_events_repo.upsert(evt)


# ── Public API ────────────────────────────────────────────────────────────────

def build_and_evaluate(
    *,
    suggestion_id: str,
    action_type: str,
    target_id: str,
    target_type: str = "task",
    parameters: dict[str, Any] | None = None,
) -> tuple[GovernableAction, GovernorDecision]:
    """
    Build a GovernableAction from caller inputs, run all gates, produce GovernorDecision.
    If decision=auto_execute, execution happens immediately inside this call.
    """
    params = parameters or {}

    # Resolve correlation / source context from suggestion
    suggestion = advisor_suggestions_repo.get(suggestion_id)
    correlation_id = suggestion.correlation_id if suggestion else None
    source_task_id = suggestion.source_task_id if suggestion else None
    if action_type == "retry_run" and not source_task_id:
        source_task_id = target_id  # task IS the target

    risk_level = _compute_risk(action_type, target_id, params)

    action = GovernableAction(
        action_id=new_id("gac"),
        suggestion_id=suggestion_id,
        action_type=action_type,  # type: ignore[arg-type]
        target_type=target_type,
        target_id=target_id,
        parameters=params,
        risk_level=risk_level,  # type: ignore[arg-type]
        idempotency_key="pending",   # real key set per decision_id below
        created_at=now_iso(),
        correlation_id=correlation_id,
    )
    governable_actions_repo.upsert(action)

    gates_passed, gates_failed, denial_reason = _evaluate_gates(action)
    decision_type = _choose_decision(risk_level, gates_failed)

    policy_snapshot = {
        "governor_enabled": get_governor_enabled(),
        "auto_execute_enabled": get_governor_auto_execute_enabled(),
        "action_type": action_type,
        "risk_level": risk_level,
        "circuit_failures": _circuit_failures.get(f"{action_type}:{target_id}", 0),
    }

    status: str
    if decision_type == "deny":
        status = "denied"
    elif decision_type == "auto_execute":
        status = "pending"   # updated to "executed" below
    else:
        status = "pending"

    decision = GovernorDecision(
        decision_id=new_id("gdec"),
        action_id=action.action_id,
        suggestion_id=suggestion_id,
        decision=decision_type,  # type: ignore[arg-type]
        reason=denial_reason or f"Decision: {decision_type}. Risk={risk_level}.",
        policy_snapshot=policy_snapshot,
        risk_level=risk_level,  # type: ignore[arg-type]
        gates_passed=gates_passed,
        gates_failed=gates_failed,
        status=status,  # type: ignore[arg-type]
        created_at=now_iso(),
        correlation_id=correlation_id,
        source_task_id=source_task_id,
    )
    governor_decisions_repo.upsert(decision)

    # Audit decision
    if decision_type == "deny":
        _audit("governor_action_denied", denial_reason or "Governor denied action", decision=decision, action=action)
    else:
        _audit("governor_decision_made", f"Governor decision: {decision_type}", decision=decision, action=action)

    # Auto-execute if gates all passed and switch is on
    if decision_type == "auto_execute":
        receipt = _run_action(action, decision)
        new_status = "executed" if receipt.outcome == "succeeded" else "failed"
        decision = decision.model_copy(update={"status": new_status, "executed_at": now_iso()})
        governor_decisions_repo.upsert(decision)

    return action, decision


def confirm_decision(decision_id: str, *, confirmed_by: str = "human") -> ExecutionReceipt:
    """Human confirms a pending require_confirmation decision.  Executes the action."""
    decision = governor_decisions_repo.get(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="governor_decision_not_found")
    if decision.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Decision is not pending (status={decision.status})",
        )
    if decision.decision != "require_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"Decision type '{decision.decision}' cannot be confirmed",
        )

    action = governable_actions_repo.get(decision.action_id)
    if not action:
        raise HTTPException(status_code=404, detail="governable_action_not_found")

    # Mark confirmed
    decision = decision.model_copy(update={"status": "confirmed", "confirmed_by": confirmed_by})
    governor_decisions_repo.upsert(decision)

    receipt = _run_action(action, decision)
    new_status = "executed" if receipt.outcome == "succeeded" else "failed"
    decision = decision.model_copy(update={"status": new_status, "executed_at": now_iso()})
    governor_decisions_repo.upsert(decision)

    return receipt


def list_decisions(status: str | None = None) -> list[GovernorDecision]:
    items = governor_decisions_repo.list()
    if status:
        items = [d for d in items if d.status == status]
    items.sort(key=lambda d: d.created_at, reverse=True)
    return items


def get_decision(decision_id: str) -> GovernorDecision | None:
    return governor_decisions_repo.get(decision_id)


def get_governor_summary() -> dict[str, Any]:
    decisions = governor_decisions_repo.list()
    receipts = governor_receipts_repo.list()
    totals = {
        "total": len(decisions),
        "pending": sum(1 for d in decisions if d.status == "pending"),
        "executed": sum(1 for d in decisions if d.status == "executed"),
        "denied": sum(1 for d in decisions if d.status == "denied"),
        "failed": sum(1 for d in decisions if d.status == "failed"),
        "auto_executed": sum(1 for d in decisions if d.decision == "auto_execute" and d.status == "executed"),
        "confirmed": sum(1 for d in decisions if d.decision == "require_confirmation" and d.status == "executed"),
    }
    recent_pending = [d for d in decisions if d.status == "pending"]
    recent_pending.sort(key=lambda d: d.created_at, reverse=True)
    return {
        "generated_at": now_iso(),
        "governor_enabled": get_governor_enabled(),
        "auto_execute_enabled": get_governor_auto_execute_enabled(),
        "totals": totals,
        "pending_decisions": recent_pending[:10],
        "recent_receipts": sorted(receipts, key=lambda r: r.executed_at, reverse=True)[:5],
        "circuit_breaker_state": dict(_circuit_failures),
    }

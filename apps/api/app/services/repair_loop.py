from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import (
    FailureType,
    RepairAction,
    RepairAttempt,
    RepairAttemptKind,
    RepairStatus,
)
from ..store.repositories import repair_attempts_repo, run_steps_repo, runs_repo, verifier_results_repo
from .runtime_audit import now_iso

MAX_RUN_STEP_RETRIES = 3
REPEATED_FAILURE_LIMIT = 2
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _validate_key(value: str | None, field: str) -> None:
    if value is None:
        return
    if not _SAFE_KEY_RE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_repair_key",
                "field": field,
                "message": "Use a stable action_key/repair_key, not a shell command string.",
            },
        )


def _loop_event(kind: RepairAttemptKind, status: RepairStatus) -> str:
    if kind == "retry":
        return "retry_blocked" if status == "blocked" else "retry_proposed"
    if kind == "trace_rollback":
        return status
    return f"repair_{status}"


def _next_attempt_index(run_step_id: str) -> int:
    existing = [item for item in repair_attempts_repo.list() if item.run_step_id == run_step_id]
    return len(existing) + 1


def _consecutive_failure_count(history: list[dict[str, Any]], failure_type: FailureType) -> int:
    count = 1
    for entry in reversed(history):
        if entry.get("failure_type") != failure_type:
            break
        count += 1
    return count


def _resolve_policy(
    *,
    attempt_kind: RepairAttemptKind,
    requested_status: RepairStatus,
    failure_type: FailureType,
    retry_count: int,
    retry_history: list[dict[str, Any]],
    high_risk: bool,
    user_confirmed: bool,
) -> tuple[RepairStatus, bool, str, str | None]:
    needs_user_confirmation = False
    safety_status = "allowed"
    block_reason: str | None = None
    status = requested_status

    if high_risk and not user_confirmed:
        status = "blocked"
        needs_user_confirmation = True
        safety_status = "needs_user_confirmation"
        block_reason = "high_risk_confirmation_required"

    if attempt_kind == "retry":
        if retry_count >= MAX_RUN_STEP_RETRIES:
            status = "blocked"
            needs_user_confirmation = True
            safety_status = "blocked"
            block_reason = "retry_limit_exceeded"
        elif _consecutive_failure_count(retry_history, failure_type) >= REPEATED_FAILURE_LIMIT:
            status = "blocked"
            needs_user_confirmation = True
            safety_status = "needs_user_confirmation"
            block_reason = "repeated_failure_type"

    return status, needs_user_confirmation, safety_status, block_reason


def create_repair_attempt(
    *,
    run_id: str,
    run_step_id: str,
    repair_action: RepairAction,
    verifier_result_id: str,
    failure_id: str | None = None,
    failure_ref: str | None = None,
    failure_type: FailureType = "unknown",
    attempt_kind: RepairAttemptKind = "repair",
    status: RepairStatus = "proposed",
    action_key: str | None = None,
    repair_key: str | None = None,
    needs_user_confirmation: bool = False,
    high_risk: bool = False,
    user_confirmed: bool = False,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RepairAttempt:
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    step = run_steps_repo.get(run_step_id)
    if not step or step.run_id != run_id:
        raise HTTPException(status_code=404, detail="run_step_not_found")
    verifier_result = verifier_results_repo.get(verifier_result_id)
    if not verifier_result:
        raise HTTPException(status_code=404, detail="verifier_result_not_found")
    if verifier_result.run_id != run_id or verifier_result.run_step_id != run_step_id:
        raise HTTPException(status_code=400, detail="verifier_result_scope_mismatch")
    if not (failure_id or failure_ref):
        raise HTTPException(status_code=400, detail="failure_id_or_failure_ref_required")
    _validate_key(action_key, "action_key")
    _validate_key(repair_key, "repair_key")

    resolved_status, policy_confirmation, safety_status, block_reason = _resolve_policy(
        attempt_kind=attempt_kind,
        requested_status=status,
        failure_type=failure_type,
        retry_count=step.retry_count,
        retry_history=step.retry_history,
        high_risk=high_risk,
        user_confirmed=user_confirmed,
    )
    needs_user_confirmation = needs_user_confirmation or policy_confirmation
    attempt_index = _next_attempt_index(run_step_id)
    clean_evidence = [item for item in (evidence_refs or []) if item.strip()]
    loop_event = _loop_event(attempt_kind, resolved_status)
    event_refs = _dedupe(
        [
            *clean_evidence,
            f"verifier_result:{verifier_result_id}",
            *(f"failure:{failure_id}" for _ in [0] if failure_id),
        ]
    )

    attempt = RepairAttempt(
        repair_attempt_id=new_id("repair"),
        run_id=run.run_id,
        run_step_id=step.run_step_id,
        task_id=step.task_id,
        verifier_result_id=verifier_result_id,
        failure_id=failure_id,
        failure_ref=failure_ref,
        failure_type=failure_type,
        attempt_index=attempt_index,
        attempt_kind=attempt_kind,
        status=resolved_status,
        repair_action=repair_action,
        action_key=action_key,
        repair_key=repair_key,
        loop_event=loop_event,
        needs_user_confirmation=needs_user_confirmation,
        high_risk=high_risk,
        safety_status=safety_status,  # type: ignore[arg-type]
        evidence_refs=event_refs,
        created_at=now_iso(),
        metadata={
            **(metadata or {}),
            **({"block_reason": block_reason} if block_reason else {}),
            "permission_profile_enforced": True,
            "action_execution": "not_executed",
        },
    )
    repair_attempts_repo.upsert(attempt)

    should_increment_retry = attempt_kind == "retry" and resolved_status not in {"blocked", "skipped"}
    retry_count = step.retry_count + 1 if should_increment_retry else step.retry_count
    retry_history = list(step.retry_history)
    if attempt_kind == "retry":
        retry_history.append(
            {
                "repair_attempt_id": attempt.repair_attempt_id,
                "attempt_index": attempt.attempt_index,
                "failure_type": failure_type,
                "status": resolved_status,
                "created_at": attempt.created_at,
                "blocked": resolved_status == "blocked",
            }
        )
    step_loop_events = list(step.metadata.get("repair_loop_events", [])) if isinstance(step.metadata, dict) else []
    step_loop_events.append(
        {
            "event": "failure_detected",
            "failure_type": failure_type,
            "repair_attempt_id": attempt.repair_attempt_id,
            "created_at": attempt.created_at,
        }
    )
    step_loop_events.append(
        {
            "event": loop_event,
            "repair_attempt_id": attempt.repair_attempt_id,
            "created_at": attempt.created_at,
        }
    )
    step_refs = _dedupe([*step.evidence_refs, *event_refs, f"repair_attempt:{attempt.repair_attempt_id}"])
    run_steps_repo.upsert(
        step.model_copy(
            update={
                "repair_ref": f"repair_attempt:{attempt.repair_attempt_id}",
                "evidence_refs": step_refs,
                "retry_count": retry_count,
                "retry_history": retry_history,
                "latest_failure_type": failure_type,
                "updated_at": now_iso(),
                "metadata": {
                    **step.metadata,
                    "latest_repair_status": attempt.status,
                    "latest_repair_attempt_id": attempt.repair_attempt_id,
                    "latest_repair_loop_event": loop_event,
                    "needs_user_confirmation": needs_user_confirmation,
                    "repair_loop_events": step_loop_events,
                },
            }
        )
    )
    return attempt


def get_repair_attempt(repair_attempt_id: str) -> RepairAttempt | None:
    return repair_attempts_repo.get(repair_attempt_id)


def list_repair_attempts(
    *,
    run_id: str | None = None,
    run_step_id: str | None = None,
    verifier_result_id: str | None = None,
    status: str | None = None,
) -> list[RepairAttempt]:
    items = repair_attempts_repo.list()
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if run_step_id:
        items = [item for item in items if item.run_step_id == run_step_id]
    if verifier_result_id:
        items = [item for item in items if item.verifier_result_id == verifier_result_id]
    if status:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda item: (item.created_at, item.repair_attempt_id), reverse=True)
    return items

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import VerifierResult, VerifierStatus, VerifierType
from ..store.repositories import run_steps_repo, runs_repo, verifier_results_repo
from .runtime_audit import now_iso

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
                "error": "invalid_verifier_key",
                "field": field,
                "message": "Use a stable command_key/check_key, not a shell command string.",
            },
        )


def _resolve_passed(status: VerifierStatus, passed: bool | None) -> bool:
    if passed is True and status != "passed":
        raise HTTPException(status_code=400, detail="passed_true_requires_status_passed")
    if status == "passed":
        if passed is False:
            raise HTTPException(status_code=400, detail="status_passed_requires_passed_true")
        return True
    return False


def create_verifier_result(
    *,
    run_id: str,
    run_step_id: str,
    verifier_type: VerifierType,
    status: VerifierStatus,
    passed: bool | None = None,
    findings: list[str] | None = None,
    command_key: str | None = None,
    check_key: str | None = None,
    output_summary: str | None = None,
    error_summary: str | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> VerifierResult:
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    step = run_steps_repo.get(run_step_id)
    if not step or step.run_id != run_id:
        raise HTTPException(status_code=404, detail="run_step_not_found")
    _validate_key(command_key, "command_key")
    _validate_key(check_key, "check_key")

    resolved_passed = _resolve_passed(status, passed)
    clean_findings = [item for item in (findings or []) if item.strip()]
    clean_evidence = [item for item in (evidence_refs or []) if item.strip()]
    if resolved_passed:
        if not (command_key or check_key):
            raise HTTPException(status_code=400, detail="passed_requires_command_key_or_check_key")
        if not (output_summary or clean_findings or clean_evidence):
            raise HTTPException(status_code=400, detail="passed_requires_success_evidence")

    result = VerifierResult(
        result_id=new_id("ver"),
        run_id=run.run_id,
        run_step_id=step.run_step_id,
        task_id=step.task_id,
        verifier_type=verifier_type,
        status=status,
        passed=resolved_passed,
        findings=clean_findings,
        command_key=command_key,
        check_key=check_key,
        output_summary=output_summary,
        error_summary=error_summary,
        evidence_refs=clean_evidence,
        created_at=now_iso(),
        metadata=metadata or {},
    )
    verifier_results_repo.upsert(result)

    result_ref = f"verifier_result:{result.result_id}"
    step_refs = _dedupe([*step.evidence_refs, *clean_evidence, result_ref])
    step_metadata = {
        **step.metadata,
        "latest_verifier_result_id": result.result_id,
        "latest_verifier_status": result.status,
        "latest_verifier_passed": result.passed,
    }
    run_steps_repo.upsert(
        step.model_copy(
            update={
                "verification_ref": result_ref,
                "evidence_refs": step_refs,
                "updated_at": now_iso(),
                "metadata": step_metadata,
            }
        )
    )
    return result


def get_verifier_result(result_id: str) -> VerifierResult | None:
    return verifier_results_repo.get(result_id)


def list_verifier_results(
    *,
    run_id: str | None = None,
    run_step_id: str | None = None,
    verifier_type: str | None = None,
    status: str | None = None,
) -> list[VerifierResult]:
    items = verifier_results_repo.list()
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if run_step_id:
        items = [item for item in items if item.run_step_id == run_step_id]
    if verifier_type:
        items = [item for item in items if item.verifier_type == verifier_type]
    if status:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items

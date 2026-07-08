from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import MemoryCompilerCandidate, MemoryCompilerRun, RepairAttempt, Run, RunStep, VerifierResult
from ..store.repositories import (
    memory_compiler_candidates_repo,
    memory_compiler_runs_repo,
    repair_attempts_repo,
    run_steps_repo,
    runs_repo,
    tasks_repo,
    verifier_results_repo,
)
from .memory_ledger import append_memory_event
from .runtime_audit import now_iso

POLICY_NAME = "default_conservative"
IMPORTANT_REPAIR_STATUSES = {"blocked", "succeeded", "rollback_completed", "rollback_failed"}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _memory_id(fingerprint: str) -> str:
    return f"memc_{fingerprint[:16]}"


def _short(value: str | None, limit: int = 900) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _steps_for_run(run_id: str) -> list[RunStep]:
    steps = [step for step in run_steps_repo.list() if step.run_id == run_id]
    steps.sort(key=lambda step: (step.sequence, step.created_at, step.run_step_id))
    return steps


def _verifiers_for_run(run_id: str) -> list[VerifierResult]:
    items = [item for item in verifier_results_repo.list() if item.run_id == run_id]
    items.sort(key=lambda item: (item.created_at, item.result_id))
    return items


def _repairs_for_run(run_id: str) -> list[RepairAttempt]:
    items = [item for item in repair_attempts_repo.list() if item.run_id == run_id]
    items.sort(key=lambda item: (item.created_at, item.repair_attempt_id))
    return items


def _candidate_from_run_result(run: Run) -> dict[str, Any] | None:
    summary = _short(run.output_excerpt)
    if run.status != "succeeded" or not summary:
        return None
    return {
        "candidate_type": "task_result_recorded",
        "subject_key": f"task:{run.task_id}:result",
        "scope_type": "task",
        "scope_id": run.task_id,
        "source_type": "run",
        "source_id": run.run_id,
        "run_id": run.run_id,
        "task_id": run.task_id,
        "content_json": {
            "memory_type": "task_result",
            "title": f"Task result for {run.task_id}",
            "summary": summary,
            "tags": ["compiler", "task_result"],
        },
        "value_json": {
            "run_status": run.status,
            "integration_path": run.integration_path,
            "output_snapshot": run.output_snapshot or {},
        },
        "evidence_refs": [f"run:{run.run_id}"],
        "confidence": 0.72,
        "policy_result": {
            "admission": "candidate",
            "policy": POLICY_NAME,
            "reason": "succeeded_run_with_output",
            "active_snapshot_eligible": True,
        },
        "metadata": {"compiler_rule": "succeeded_run_result"},
    }


def _candidate_from_verifier(result: VerifierResult) -> dict[str, Any] | None:
    if result.status not in {"failed", "blocked"}:
        return None
    refs = _dedupe([f"run_step:{result.run_step_id}", f"verifier_result:{result.result_id}", *result.evidence_refs])
    return {
        "candidate_type": "verification_recorded",
        "subject_key": f"run:{result.run_id}:verifier:{result.verifier_type}:{result.status}",
        "scope_type": "task",
        "scope_id": result.task_id,
        "source_type": "verifier_result",
        "source_id": result.result_id,
        "run_id": result.run_id,
        "run_step_id": result.run_step_id,
        "task_id": result.task_id,
        "content_json": {
            "memory_type": "verification",
            "title": f"{result.verifier_type} verifier {result.status}",
            "findings": result.findings,
            "output_summary": _short(result.output_summary),
            "error_summary": _short(result.error_summary),
            "tags": ["compiler", "verification"],
        },
        "value_json": {
            "verifier_type": result.verifier_type,
            "status": result.status,
            "passed": result.passed,
            "command_key": result.command_key,
            "check_key": result.check_key,
        },
        "evidence_refs": refs,
        "confidence": 0.68,
        "policy_result": {
            "admission": "candidate",
            "policy": POLICY_NAME,
            "reason": "failed_or_blocked_verifier",
            "active_snapshot_eligible": False,
        },
        "metadata": {"compiler_rule": "failed_or_blocked_verifier"},
    }


def _candidate_from_repair(attempt: RepairAttempt) -> dict[str, Any] | None:
    if attempt.status not in IMPORTANT_REPAIR_STATUSES:
        return None
    if attempt.attempt_kind == "retry" and attempt.status != "blocked":
        return None
    candidate_type = "decision_recorded" if attempt.status in {"succeeded", "rollback_completed"} else "failure_recorded"
    refs = _dedupe(
        [
            f"run_step:{attempt.run_step_id}",
            f"repair_attempt:{attempt.repair_attempt_id}",
            f"verifier_result:{attempt.verifier_result_id}",
            *attempt.evidence_refs,
        ]
    )
    return {
        "candidate_type": candidate_type,
        "subject_key": f"run_step:{attempt.run_step_id}:repair:{attempt.failure_type}:{attempt.status}",
        "scope_type": "task",
        "scope_id": attempt.task_id,
        "source_type": "repair_attempt",
        "source_id": attempt.repair_attempt_id,
        "run_id": attempt.run_id,
        "run_step_id": attempt.run_step_id,
        "task_id": attempt.task_id,
        "failure_id": attempt.failure_id,
        "content_json": {
            "memory_type": "repair_outcome" if candidate_type == "decision_recorded" else "failure",
            "title": f"{attempt.attempt_kind} {attempt.status}: {attempt.failure_type}",
            "failure_ref": attempt.failure_ref,
            "loop_event": attempt.loop_event,
            "tags": ["compiler", "repair"],
        },
        "value_json": {
            "failure_type": attempt.failure_type,
            "attempt_kind": attempt.attempt_kind,
            "status": attempt.status,
            "repair_action": attempt.repair_action,
            "action_key": attempt.action_key,
            "repair_key": attempt.repair_key,
            "needs_user_confirmation": attempt.needs_user_confirmation,
            "high_risk": attempt.high_risk,
            "safety_status": attempt.safety_status,
        },
        "evidence_refs": refs,
        "confidence": 0.7 if candidate_type == "decision_recorded" else 0.62,
        "policy_result": {
            "admission": "candidate",
            "policy": POLICY_NAME,
            "reason": "important_repair_outcome",
            "retry_spam_guard": "only_blocked_retry_or_terminal_repair",
            "active_snapshot_eligible": False,
        },
        "metadata": {"compiler_rule": "important_repair_outcome"},
    }


def _candidate_from_skill_step(step: RunStep) -> dict[str, Any] | None:
    if not step.skill_id or step.status != "succeeded":
        return None
    refs = _dedupe(
        [
            f"run_step:{step.run_step_id}",
            *(step.evidence_refs or []),
            *(["output_ref:" + step.output_ref] if step.output_ref else []),
        ]
    )
    if len(refs) <= 1:
        return None
    return {
        "candidate_type": "skill_result_recorded",
        "subject_key": f"skill:{step.skill_id}:task:{step.task_id}",
        "scope_type": "task",
        "scope_id": step.task_id,
        "source_type": "run_step",
        "source_id": step.run_step_id,
        "run_id": step.run_id,
        "run_step_id": step.run_step_id,
        "task_id": step.task_id,
        "skill_id": step.skill_id,
        "content_json": {
            "memory_type": "skill_result",
            "title": f"Skill result for {step.skill_id}",
            "output_ref": step.output_ref,
            "tags": ["compiler", "skill"],
        },
        "value_json": {
            "skill_id": step.skill_id,
            "step_status": step.status,
            "tool_call_id": step.tool_call_id,
        },
        "evidence_refs": refs,
        "confidence": 0.66,
        "policy_result": {
            "admission": "candidate",
            "policy": POLICY_NAME,
            "reason": "succeeded_skill_step_with_existing_evidence",
            "active_snapshot_eligible": False,
        },
        "metadata": {"compiler_rule": "skill_step_existing_evidence"},
    }


def _store_candidate(compiler_run_id: str, spec: dict[str, Any]) -> MemoryCompilerCandidate | None:
    fingerprint = _fingerprint(
        {
            "candidate_type": spec["candidate_type"],
            "subject_key": spec["subject_key"],
            "source_type": spec.get("source_type"),
            "source_id": spec.get("source_id"),
            "value_json": spec.get("value_json", {}),
            "evidence_refs": spec.get("evidence_refs", []),
        }
    )
    if any(candidate.fingerprint == fingerprint for candidate in memory_compiler_candidates_repo.list()):
        return None
    candidate = MemoryCompilerCandidate(
        candidate_id=new_id("memcand"),
        compiler_run_id=compiler_run_id,
        memory_id=_memory_id(fingerprint),
        fingerprint=fingerprint,
        created_at=now_iso(),
        **spec,
    )
    return memory_compiler_candidates_repo.upsert(candidate)


def _collect_candidates(compiler_run_id: str, runs: list[Run], max_candidates: int) -> list[MemoryCompilerCandidate]:
    created: list[MemoryCompilerCandidate] = []
    for run in runs:
        specs: list[dict[str, Any]] = []
        run_result = _candidate_from_run_result(run)
        if run_result:
            specs.append(run_result)
        specs.extend(
            candidate
            for candidate in (_candidate_from_verifier(result) for result in _verifiers_for_run(run.run_id))
            if candidate
        )
        specs.extend(
            candidate
            for candidate in (_candidate_from_repair(attempt) for attempt in _repairs_for_run(run.run_id))
            if candidate
        )
        specs.extend(
            candidate
            for candidate in (_candidate_from_skill_step(step) for step in _steps_for_run(run.run_id))
            if candidate
        )
        for spec in specs:
            if len(created) >= max_candidates:
                return created
            candidate = _store_candidate(compiler_run_id, spec)
            if candidate:
                created.append(candidate)
    return created


def run_memory_compiler(
    *,
    run_id: str | None = None,
    task_id: str | None = None,
    dry_run: bool = True,
    max_candidates: int = 20,
    metadata: dict[str, Any] | None = None,
) -> tuple[MemoryCompilerRun, list[MemoryCompilerCandidate]]:
    if not dry_run:
        raise HTTPException(status_code=400, detail="compiler_run_requires_dry_run_true_commit_candidates_explicitly")
    if not (run_id or task_id):
        raise HTTPException(status_code=400, detail="run_id_or_task_id_required")

    runs: list[Run]
    scope_type = "run" if run_id else "task"
    scope_id = run_id or task_id or ""
    if run_id:
        run = runs_repo.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run_not_found")
        if task_id and run.task_id != task_id:
            raise HTTPException(status_code=400, detail="run_task_scope_mismatch")
        task_id = run.task_id
        runs = [run]
    else:
        if not task_id or not tasks_repo.get(task_id):
            raise HTTPException(status_code=404, detail="task_not_found")
        runs = [run for run in runs_repo.list() if run.task_id == task_id]
        runs.sort(key=lambda run: (run.finished_at or run.started_at or run.queued_at or "", run.run_id))

    started_at = now_iso()
    compiler_run = MemoryCompilerRun(
        compiler_run_id=new_id("memcomp"),
        scope_type=scope_type,  # type: ignore[arg-type]
        scope_id=scope_id,
        run_id=run_id,
        task_id=task_id,
        dry_run=True,
        status="completed",
        policy_name=POLICY_NAME,
        started_at=started_at,
        finished_at=started_at,
        metadata={
            **(metadata or {}),
            "auto_commit": "disabled",
            "legacy_task_lifecycle_memory_path": "unchanged",
        },
    )
    memory_compiler_runs_repo.upsert(compiler_run)
    candidates = _collect_candidates(compiler_run.compiler_run_id, runs, max_candidates)
    finished_at = now_iso()
    compiler_run = memory_compiler_runs_repo.upsert(
        compiler_run.model_copy(
            update={
                "candidates_created": len(candidates),
                "finished_at": finished_at,
            }
        )
    )
    return compiler_run, candidates


def get_memory_compiler_run(compiler_run_id: str) -> MemoryCompilerRun | None:
    return memory_compiler_runs_repo.get(compiler_run_id)


def list_memory_compiler_runs(
    *,
    run_id: str | None = None,
    task_id: str | None = None,
) -> list[MemoryCompilerRun]:
    items = memory_compiler_runs_repo.list()
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if task_id:
        items = [item for item in items if item.task_id == task_id]
    items.sort(key=lambda item: item.started_at, reverse=True)
    return items


def get_memory_compiler_candidate(candidate_id: str) -> MemoryCompilerCandidate | None:
    return memory_compiler_candidates_repo.get(candidate_id)


def list_memory_compiler_candidates(
    *,
    compiler_run_id: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    candidate_type: str | None = None,
) -> list[MemoryCompilerCandidate]:
    items = memory_compiler_candidates_repo.list()
    if compiler_run_id:
        items = [item for item in items if item.compiler_run_id == compiler_run_id]
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if task_id:
        items = [item for item in items if item.task_id == task_id]
    if status:
        items = [item for item in items if item.status == status]
    if candidate_type:
        items = [item for item in items if item.candidate_type == candidate_type]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def commit_memory_compiler_candidate(
    candidate_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> tuple[MemoryCompilerCandidate, Any]:
    candidate = memory_compiler_candidates_repo.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="memory_compiler_candidate_not_found")
    if candidate.status == "committed":
        raise HTTPException(status_code=400, detail="memory_compiler_candidate_already_committed")
    if candidate.status != "proposed":
        raise HTTPException(status_code=400, detail="memory_compiler_candidate_not_proposed")

    event = append_memory_event(
        event_type=candidate.candidate_type,
        memory_id=candidate.memory_id,
        subject_key=candidate.subject_key,
        scope_type=candidate.scope_type,
        scope_id=candidate.scope_id,
        source_type=candidate.source_type,
        source_id=candidate.source_id,
        run_id=candidate.run_id,
        run_step_id=candidate.run_step_id,
        task_id=candidate.task_id,
        conversation_id=candidate.conversation_id,
        skill_id=candidate.skill_id,
        decision_id=candidate.decision_id,
        failure_id=candidate.failure_id,
        content_json=candidate.content_json,
        value_json=candidate.value_json,
        evidence_refs=candidate.evidence_refs,
        confidence=candidate.confidence,
        policy_result=candidate.policy_result,
        supersedes_event_id=candidate.supersedes_event_id,
        invalidates_event_id=candidate.invalidates_event_id,
        created_by="ai",
        metadata={
            **candidate.metadata,
            **(metadata or {}),
            "compiler_candidate_id": candidate.candidate_id,
            "compiler_run_id": candidate.compiler_run_id,
            "compiler_commit": True,
        },
    )
    updated = memory_compiler_candidates_repo.upsert(
        candidate.model_copy(
            update={
                "status": "committed",
                "committed_event_id": event.event_id,
                "committed_at": now_iso(),
                "metadata": {
                    **candidate.metadata,
                    **(metadata or {}),
                    "committed_memory_event_id": event.event_id,
                },
            }
        )
    )
    compiler_run = memory_compiler_runs_repo.get(candidate.compiler_run_id)
    if compiler_run:
        memory_compiler_runs_repo.upsert(
            compiler_run.model_copy(update={"candidates_committed": compiler_run.candidates_committed + 1})
        )
    return updated, event

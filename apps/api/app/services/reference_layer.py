from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import AggregatorDecision, ReferenceCandidate, ReferenceRole
from ..store.repositories import aggregator_decisions_repo, reference_candidates_repo, run_steps_repo, runs_repo
from .runtime_audit import now_iso

REFERENCE_ROLES: tuple[ReferenceRole, ...] = (
    "architect_reviewer",
    "implementation_reviewer",
    "security_reviewer",
    "test_reviewer",
    "docs_reviewer",
)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _get_run_and_step(run_id: str, run_step_id: str):
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    step = run_steps_repo.get(run_step_id)
    if not step or step.run_id != run_id:
        raise HTTPException(status_code=404, detail="run_step_not_found")
    return run, step


def create_reference_candidate(
    *,
    run_id: str,
    run_step_id: str,
    agent_role: ReferenceRole,
    summary: str,
    risks: list[str] | None = None,
    recommended_plan: list[str] | None = None,
    files_to_touch: list[str] | None = None,
    confidence: float = 0.0,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReferenceCandidate:
    run, step = _get_run_and_step(run_id, run_step_id)
    candidate = ReferenceCandidate(
        candidate_id=new_id("refcand"),
        run_id=run.run_id,
        run_step_id=step.run_step_id,
        task_id=step.task_id,
        agent_role=agent_role,
        summary=summary,
        risks=risks or [],
        recommended_plan=recommended_plan or [],
        files_to_touch=files_to_touch or [],
        confidence=confidence,
        evidence_refs=evidence_refs or [],
        created_at=now_iso(),
        metadata=metadata or {},
    )
    return reference_candidates_repo.upsert(candidate)


def get_reference_candidate(candidate_id: str) -> ReferenceCandidate | None:
    return reference_candidates_repo.get(candidate_id)


def list_reference_candidates(
    *,
    run_id: str | None = None,
    run_step_id: str | None = None,
) -> list[ReferenceCandidate]:
    items = reference_candidates_repo.list()
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if run_step_id:
        items = [item for item in items if item.run_step_id == run_step_id]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def get_aggregator_decision(aggregation_id: str) -> AggregatorDecision | None:
    return aggregator_decisions_repo.get(aggregation_id)


def list_aggregator_decisions(
    *,
    run_id: str | None = None,
    run_step_id: str | None = None,
) -> list[AggregatorDecision]:
    items = aggregator_decisions_repo.list()
    if run_id:
        items = [item for item in items if item.run_id == run_id]
    if run_step_id:
        items = [item for item in items if item.run_step_id == run_step_id]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def _candidate_pool(
    *,
    run_id: str,
    run_step_id: str,
    candidate_ids: list[str] | None = None,
) -> list[ReferenceCandidate]:
    if candidate_ids is None:
        return [
            item
            for item in reference_candidates_repo.list()
            if item.run_id == run_id and item.run_step_id == run_step_id
        ]
    wanted = set(candidate_ids)
    items = [item for item in reference_candidates_repo.list() if item.candidate_id in wanted]
    found = {item.candidate_id for item in items}
    missing = [candidate_id for candidate_id in candidate_ids if candidate_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail={"error": "reference_candidate_not_found", "candidate_ids": missing})
    invalid = [item.candidate_id for item in items if item.run_id != run_id or item.run_step_id != run_step_id]
    if invalid:
        raise HTTPException(status_code=400, detail={"error": "reference_candidate_scope_mismatch", "candidate_ids": invalid})
    return items


def _merge_selected_plan(candidates: list[ReferenceCandidate], selected: ReferenceCandidate) -> list[str]:
    plan: list[str] = []
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        plan.extend(candidate.recommended_plan)
    if not plan:
        plan.append(selected.summary)
    return _dedupe([item for item in plan if item.strip()])


def _detect_conflicts(candidates: list[ReferenceCandidate]) -> list[str]:
    conflicts: list[str] = []
    if not candidates:
        return conflicts
    confidences = [item.confidence for item in candidates]
    if max(confidences) - min(confidences) >= 0.4:
        conflicts.append("reference_confidence_spread")
    for candidate in candidates:
        for risk in candidate.risks:
            if risk.lower().startswith("conflict:"):
                conflicts.append(f"{candidate.agent_role}:{risk}")
    return _dedupe(conflicts)


def _default_known_gaps(candidates: list[ReferenceCandidate]) -> list[str]:
    roles_seen = {candidate.agent_role for candidate in candidates}
    missing = [role for role in REFERENCE_ROLES if role not in roles_seen]
    if not missing:
        return []
    return [f"missing_reference_roles:{','.join(missing)}"]


def _default_verifier_requirements(candidates: list[ReferenceCandidate]) -> list[str]:
    roles_seen = {candidate.agent_role for candidate in candidates}
    requirements: list[str] = []
    if "test_reviewer" in roles_seen:
        requirements.append("Run baseline checks before accepting the selected plan.")
    if "security_reviewer" in roles_seen:
        requirements.append("Review permission and secret-handling impact before execution.")
    return requirements


def create_aggregator_decision(
    *,
    run_id: str,
    run_step_id: str,
    candidate_ids: list[str] | None = None,
    requires_user_confirmation: bool | None = None,
    known_gaps: list[str] | None = None,
    verifier_requirements: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AggregatorDecision:
    run, step = _get_run_and_step(run_id, run_step_id)
    candidates = _candidate_pool(run_id=run.run_id, run_step_id=step.run_step_id, candidate_ids=candidate_ids)
    if not candidates:
        raise HTTPException(status_code=400, detail="no_reference_candidates")

    candidates.sort(key=lambda item: (item.confidence, item.created_at, item.candidate_id), reverse=True)
    selected = candidates[0]
    conflicts = _detect_conflicts(candidates)
    confidence = round(sum(item.confidence for item in candidates) / len(candidates), 3)
    selected_plan = _merge_selected_plan(candidates, selected)
    gaps = _dedupe([*(known_gaps or []), *_default_known_gaps(candidates)])
    verifier = _dedupe([*(verifier_requirements or []), *_default_verifier_requirements(candidates)])
    rejected = [
        {
            "candidate_id": candidate.candidate_id,
            "agent_role": candidate.agent_role,
            "reason": "lower_confidence_or_conflict",
        }
        for candidate in candidates
        if candidate.candidate_id != selected.candidate_id
    ]
    if requires_user_confirmation is None:
        requires_user_confirmation = bool(conflicts) or confidence < 0.65
    evidence_refs = _dedupe(
        [
            *(f"reference_candidate:{candidate.candidate_id}" for candidate in candidates),
            *(ref for candidate in candidates for ref in candidate.evidence_refs),
        ]
    )

    decision = AggregatorDecision(
        aggregation_id=new_id("aggr"),
        run_id=run.run_id,
        run_step_id=step.run_step_id,
        task_id=step.task_id,
        candidates_considered=[candidate.candidate_id for candidate in candidates],
        selected_plan=selected_plan,
        rejected_candidates=rejected,
        consensus=f"Selected {selected.agent_role} as the lead reference from {len(candidates)} candidate(s).",
        conflicts=conflicts,
        confidence=confidence,
        known_gaps=gaps,
        verifier_requirements=verifier,
        requires_user_confirmation=requires_user_confirmation,
        evidence_refs=evidence_refs,
        created_at=now_iso(),
        metadata=metadata or {},
    )
    aggregator_decisions_repo.upsert(decision)

    for candidate in candidates:
        status = "selected" if candidate.candidate_id == selected.candidate_id else "rejected"
        reference_candidates_repo.upsert(candidate.model_copy(update={"status": status}))

    step_refs = _dedupe([*step.evidence_refs, *evidence_refs, f"reference_aggregation:{decision.aggregation_id}"])
    step_metadata = {
        **step.metadata,
        "reference_aggregation_id": decision.aggregation_id,
        "reference_candidates_considered": decision.candidates_considered,
    }
    run_steps_repo.upsert(
        step.model_copy(
            update={
                "decision_id": decision.aggregation_id,
                "output_ref": f"reference_aggregation:{decision.aggregation_id}",
                "evidence_refs": step_refs,
                "updated_at": now_iso(),
                "metadata": step_metadata,
            }
        )
    )
    return decision

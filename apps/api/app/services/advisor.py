from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import AdvisorSuggestion, WatchdogEvent
from ..store.repositories import advisor_suggestions_repo, skills_repo, task_events_repo, tasks_repo, watchdog_events_repo
from .policy_engine import build_policy_explanation
from .runtime_audit import append_task_event, now_iso

# P2-C: suggestions older than this are lazily expired
_EXPIRY_DAYS = 7

# P2-C: next-step guidance shown to operator after accepting a suggestion
_NEXT_ACTION_MAP: dict[str, tuple[str, str]] = {
    "recovery_suggestion": (
        "Review the task timeline and retry or resolve the issue manually.",
        "/tasks",
    ),
    "failure_pattern": (
        "Inspect run logs and investigate the recurring failure pattern.",
        "/runs",
    ),
    "best_practice_candidate": (
        "Review this candidate practice and consider applying it to your workflow.",
        "/policies",
    ),
    "policy_draft_suggestion": (
        "Open the Policies page to review and adjust the execution policy.",
        "/policies",
    ),
}


def _stable_suggestion_id(*parts: str | None) -> str:
    raw = "|".join((part or "_") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"adv_{digest}"


def _dedupe_evidence_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _effective_pattern_key(suggestion: AdvisorSuggestion) -> str:
    if suggestion.pattern_key:
        return suggestion.pattern_key
    if suggestion.issue_class:
        return suggestion.issue_class
    return f"{suggestion.suggestion_type}:{suggestion.target_type}"


def _lookup_watchdog_event(event_id: str | None) -> WatchdogEvent | None:
    if not event_id:
        return None
    return watchdog_events_repo.get(event_id)


def _count_skill_confirm_blocks(skill_id: str) -> int:
    return sum(
        1
        for event in task_events_repo.list()
        if event.type == "skill_blocked" and (event.payload or {}).get("skill_id") == skill_id
    )


def _suggestion_occurrence_units(suggestion: AdvisorSuggestion) -> tuple[int, str | None, bool]:
    effective_last_seen = suggestion.updated_at or suggestion.created_at
    watchdog_event = _lookup_watchdog_event(suggestion.source_watchdog_event_id)
    if watchdog_event:
        effective_last_seen = watchdog_event.last_seen_at or watchdog_event.created_at or effective_last_seen
        has_attention_or_escalation = watchdog_event.issue_status in ("processing", "escalated")
        return max(watchdog_event.occurrence_count or 1, 1), effective_last_seen, has_attention_or_escalation

    if suggestion.pattern_key and suggestion.pattern_key.startswith("skill_confirm_gate:"):
        blocked_count = _count_skill_confirm_blocks(suggestion.target_id)
        if blocked_count > 0:
            return blocked_count, effective_last_seen, False

    task = tasks_repo.get(suggestion.source_task_id) if suggestion.source_task_id else None
    has_attention_or_escalation = bool(task and task.needs_attention)
    return 1, effective_last_seen, has_attention_or_escalation


def _build_pattern_stats(items: list[AdvisorSuggestion]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for suggestion in items:
        pattern_key = _effective_pattern_key(suggestion)
        occurrence_units, last_seen_at, has_attention_or_escalation = _suggestion_occurrence_units(suggestion)
        bucket = stats.setdefault(
            pattern_key,
            {
                "occurrence_count": 0,
                "last_seen_at": suggestion.updated_at or suggestion.created_at,
                "affected_targets": set(),
                "high_signal": False,
            },
        )
        bucket["occurrence_count"] += max(occurrence_units, 1)
        candidate_last_seen = last_seen_at or suggestion.updated_at or suggestion.created_at
        if candidate_last_seen and candidate_last_seen > (bucket["last_seen_at"] or ""):
            bucket["last_seen_at"] = candidate_last_seen
        bucket["affected_targets"].add((suggestion.target_type, suggestion.target_id))
        bucket["high_signal"] = bucket["high_signal"] or has_attention_or_escalation
    return stats


def _confidence_for(*, occurrence_count: int, high_signal: bool) -> str:
    if occurrence_count <= 1:
        return "low"
    if high_signal:
        return "high"
    return "medium"


def _build_policy_preview(suggestion: AdvisorSuggestion) -> dict[str, Any] | None:
    if suggestion.suggestion_type != "policy_draft_suggestion" or suggestion.target_type != "skill":
        return None
    skill = skills_repo.get(suggestion.target_id)
    if not skill:
        return None
    explanation = build_policy_explanation("skill", skill.skill_id)
    suggested_mode = "notify" if explanation.effective_mode == "confirm" else explanation.effective_mode
    target_scope = "skill_default" if explanation.policy_source == "skill_default" else (explanation.matched_policy_scope or "global")
    suggested_change = (
        f"Set skill default_execution_policy to {suggested_mode}."
        if explanation.policy_source == "skill_default"
        else f"Review matched policy {explanation.matched_policy_id or 'enforced_policy'} before keeping confirm friction in place."
    )
    return {
        "preview_type": "skill_execution_policy_review",
        "target_scope": target_scope,
        "target_label": skill.name,
        "current_effective_mode": explanation.effective_mode,
        "current_default_execution_policy": skill.default_execution_policy,
        "suggested_mode": suggested_mode,
        "matched_policy_id": explanation.matched_policy_id,
        "policy_source": explanation.policy_source,
        "precedence": explanation.precedence,
        "reason": explanation.reason,
        "suggested_change": suggested_change,
    }


def _with_query_time_insights(items: list[AdvisorSuggestion]) -> list[AdvisorSuggestion]:
    pattern_stats = _build_pattern_stats(items)
    enriched: list[AdvisorSuggestion] = []
    for suggestion in items:
        pattern_key = _effective_pattern_key(suggestion)
        stats = pattern_stats[pattern_key]
        enriched.append(
            suggestion.model_copy(
                update={
                    "pattern_key": pattern_key,
                    "occurrence_count": int(stats["occurrence_count"]),
                    "last_seen_at": stats["last_seen_at"],
                    "affected_targets": len(stats["affected_targets"]),
                    "confidence": _confidence_for(
                        occurrence_count=int(stats["occurrence_count"]),
                        high_signal=bool(stats["high_signal"]),
                    ),
                    "policy_preview": _build_policy_preview(suggestion),
                }
            )
        )
    return enriched


def _build_pattern_summary(items: list[AdvisorSuggestion], *, limit: int = 5) -> list[dict[str, Any]]:
    stats = _build_pattern_stats(items)
    out: list[dict[str, Any]] = []
    for pattern_key, bucket in stats.items():
        occurrence_count = int(bucket["occurrence_count"])
        out.append(
            {
                "pattern_key": pattern_key,
                "occurrence_count": occurrence_count,
                "last_seen_at": bucket["last_seen_at"],
                "affected_targets": len(bucket["affected_targets"]),
                "confidence": _confidence_for(
                    occurrence_count=occurrence_count,
                    high_signal=bool(bucket["high_signal"]),
                ),
            }
        )
    out.sort(key=lambda item: (item["occurrence_count"], item["last_seen_at"] or ""), reverse=True)
    return out[:limit]


def _build_policy_suggestion_summary(items: list[AdvisorSuggestion], *, limit: int = 4) -> list[dict[str, Any]]:
    policy_items = [item for item in items if item.suggestion_type == "policy_draft_suggestion" and item.policy_preview]
    policy_items.sort(
        key=lambda item: (item.occurrence_count or 1, item.updated_at or item.created_at),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for item in policy_items[:limit]:
        preview = item.policy_preview or {}
        out.append(
            {
                "suggestion_id": item.suggestion_id,
                "title": item.title,
                "status": item.status,
                "severity": item.severity,
                "confidence": item.confidence,
                "occurrence_count": item.occurrence_count or 1,
                "target_id": item.target_id,
                "target_label": preview.get("target_label"),
                "current_effective_mode": preview.get("current_effective_mode"),
                "suggested_mode": preview.get("suggested_mode"),
                "matched_policy_id": preview.get("matched_policy_id"),
                "policy_source": preview.get("policy_source"),
            }
        )
    return out


def _append_watchdog_audit(
    event_type: str,
    message: str,
    *,
    suggestion: AdvisorSuggestion,
    source: str,
) -> WatchdogEvent:
    event = WatchdogEvent(
        event_id=new_id("wd"),
        type=event_type,
        message=message,
        created_at=now_iso(),
        severity="info",
        task_id=suggestion.source_task_id,
        agent_id=None,
        correlation_id=suggestion.correlation_id,
        source=source,  # type: ignore[arg-type]
        issue_status="resolved",
        suggested_action="advisor_review",
        issue_class=suggestion.issue_class,
        related_run_id=suggestion.source_run_id,
        parent_run_id=None,
    )
    watchdog_events_repo.upsert(event)
    return event


def _append_suggestion_audit(
    event_type: str,
    message: str,
    *,
    suggestion: AdvisorSuggestion,
    source: str,
) -> None:
    if suggestion.source_task_id:
        append_task_event(
            suggestion.source_task_id,
            event_type,
            message,
            correlation_id=suggestion.correlation_id,
            payload={
                "suggestion_id": suggestion.suggestion_id,
                "suggestion_type": suggestion.suggestion_type,
                "target_type": suggestion.target_type,
                "target_id": suggestion.target_id,
                "issue_class": suggestion.issue_class,
                "pattern_key": suggestion.pattern_key,
                "status": suggestion.status,
            },
        )
        return
    _append_watchdog_audit(event_type, message, suggestion=suggestion, source=source)


def upsert_advisor_suggestion(
    *,
    suggestion_type: str,
    target_type: str,
    target_id: str,
    title: str,
    summary: str,
    rationale: str,
    recommended_action: str,
    evidence_refs: list[dict[str, Any]],
    severity: str = "warning",
    requires_confirmation: bool = False,
    issue_class: str | None = None,
    pattern_key: str | None = None,
    correlation_id: str | None = None,
    source_task_id: str | None = None,
    source_run_id: str | None = None,
    source_watchdog_event_id: str | None = None,
) -> AdvisorSuggestion:
    pattern_key = pattern_key or issue_class or f"{suggestion_type}:{target_type}"
    suggestion_id = _stable_suggestion_id(
        suggestion_type,
        target_type,
        target_id,
        issue_class,
        pattern_key,
    )
    now = now_iso()
    existing = advisor_suggestions_repo.get(suggestion_id)
    next_status = "open"
    is_new_or_reopened = existing is None or existing.status != "open"
    merged_evidence = _dedupe_evidence_refs(
        [
            *(existing.evidence_refs if existing else []),
            *evidence_refs,
        ]
    )
    suggestion = AdvisorSuggestion(
        suggestion_id=suggestion_id,
        suggestion_type=suggestion_type,  # type: ignore[arg-type]
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        issue_class=issue_class,
        pattern_key=pattern_key,
        title=title,
        summary=summary,
        rationale=rationale,
        recommended_action=recommended_action,
        evidence_refs=merged_evidence,
        status=next_status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        requires_confirmation=requires_confirmation,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        correlation_id=correlation_id or (existing.correlation_id if existing else None),
        source_task_id=source_task_id or (existing.source_task_id if existing else None),
        source_run_id=source_run_id or (existing.source_run_id if existing else None),
        source_watchdog_event_id=source_watchdog_event_id or (existing.source_watchdog_event_id if existing else None),
    )
    advisor_suggestions_repo.upsert(suggestion)
    if is_new_or_reopened:
        _append_suggestion_audit(
            "advisor_suggestion_generated",
            title,
            suggestion=suggestion,
            source="advisor",
        )
    return suggestion


def _apply_lazy_expiry(items: list[AdvisorSuggestion]) -> list[AdvisorSuggestion]:
    """P2-C: Mark open suggestions older than _EXPIRY_DAYS as expired (lazy, on read)."""
    now = datetime.now(tz=timezone.utc)
    threshold = now - timedelta(days=_EXPIRY_DAYS)
    result: list[AdvisorSuggestion] = []
    for s in items:
        if s.status != "open":
            result.append(s)
            continue
        try:
            created = datetime.fromisoformat(s.created_at.replace("Z", "+00:00"))
            if created < threshold:
                expired = s.model_copy(update={"status": "expired", "updated_at": now_iso()})
                advisor_suggestions_repo.upsert(expired)
                result.append(expired)
                continue
        except Exception:  # noqa: BLE001
            pass
        result.append(s)
    return result


def list_advisor_suggestions(
    *,
    status: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    suggestion_type: str | None = None,
) -> list[AdvisorSuggestion]:
    raw = advisor_suggestions_repo.list()
    raw = _apply_lazy_expiry(raw)          # P2-C: expire stale open suggestions
    items = _with_query_time_insights(raw)
    if status:
        items = [item for item in items if item.status == status]
    if target_type:
        items = [item for item in items if item.target_type == target_type]
    if target_id:
        items = [item for item in items if item.target_id == target_id]
    if suggestion_type:
        items = [item for item in items if item.suggestion_type == suggestion_type]
    items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return items


def build_advisor_summary(*, limit: int = 6) -> dict[str, Any]:
    items = list_advisor_suggestions()
    open_first = [item for item in items if item.status == "open"]
    if len(open_first) < limit:
        open_first.extend(item for item in items if item.status != "open")
    totals = {
        "total": len(items),
        "open": sum(1 for item in items if item.status == "open"),
        "accepted": sum(1 for item in items if item.status == "accepted"),
        "dismissed": sum(1 for item in items if item.status == "dismissed"),
        "critical": sum(1 for item in items if item.severity == "critical"),
    }
    return {
        "generated_at": now_iso(),
        "totals": totals,
        "top_suggestions": open_first[:limit],
        "pattern_summary": _build_pattern_summary(items),
        "policy_suggestion_summary": _build_policy_suggestion_summary(items),
    }


def build_task_advice(task_id: str) -> list[AdvisorSuggestion]:
    items = [item for item in list_advisor_suggestions() if item.target_type == "task" and item.target_id == task_id]
    items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return items


def _update_suggestion_status(suggestion_id: str, *, status: str) -> AdvisorSuggestion:
    suggestion = advisor_suggestions_repo.get(suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="advisor_suggestion_not_found")
    updates: dict[str, Any] = {"status": status, "updated_at": now_iso()}
    # P2-C: populate acceptance path hints on accept
    if status == "accepted":
        hint, url = _NEXT_ACTION_MAP.get(
            suggestion.suggestion_type,
            ("Review system state and take corrective action.", "/watchdog"),
        )
        updates["next_action_hint"] = hint
        updates["next_action_url"] = url
    updated = suggestion.model_copy(update=updates)
    advisor_suggestions_repo.upsert(updated)
    if status == "accepted":
        _append_suggestion_audit(
            "advisor_suggestion_accepted",
            updated.title,
            suggestion=updated,
            source="human",
        )
    elif status == "dismissed":
        _append_suggestion_audit(
            "advisor_suggestion_dismissed",
            updated.title,
            suggestion=updated,
            source="human",
        )
    return updated


def accept_advisor_suggestion(suggestion_id: str) -> AdvisorSuggestion:
    return _update_suggestion_status(suggestion_id, status="accepted")


def dismiss_advisor_suggestion(suggestion_id: str) -> AdvisorSuggestion:
    return _update_suggestion_status(suggestion_id, status="dismissed")

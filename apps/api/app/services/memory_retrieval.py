from __future__ import annotations

import json
from typing import Any, Callable

from ..store.repositories import (
    active_memory_snapshots_repo,
    advisor_suggestions_repo,
    conversation_messages_repo,
    conversations_repo,
    file_artifacts_repo,
    governor_decisions_repo,
    governor_receipts_repo,
    memory_events_repo,
    memory_index_repo,
    memory_repo,
    reports_repo,
    run_logs_repo,
    run_steps_repo,
    runs_repo,
    skills_repo,
    task_events_repo,
    tasks_repo,
    watchdog_events_repo,
    master_tasks_repo,
)
from .memory_ledger import rebuild_active_snapshot

DEFAULT_EVIDENCE_LIMIT = 12
MAX_EVIDENCE_LIMIT = 50
DEFAULT_CHAR_BUDGET = 12000
MAX_CHAR_BUDGET = 50000
DATA_STRING_LIMIT = 1000
LIST_ITEM_LIMIT = 20

NATIVE_EVIDENCE_SOURCES = {
    "workspace",
    "raw_logs",
    "conversation_logs",
    "task_logs",
    "evidence",
    "summaries",
    "memory_events",
    "run_logs",
    "skills",
    "decisions",
    "failures",
}


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _clip_text(value: str, limit: int = DATA_STRING_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _safe_data(value: Any) -> Any:
    value = _model_dump(value)
    if isinstance(value, str):
        return _clip_text(value)
    if isinstance(value, list):
        return [_safe_data(item) for item in value[:LIST_ITEM_LIMIT]]
    if isinstance(value, dict):
        return {str(key): _safe_data(item) for key, item in value.items()}
    return value


def _json_text(value: Any) -> str:
    return json.dumps(_model_dump(value), ensure_ascii=False, default=str, sort_keys=True)


def _json_len(value: Any) -> int:
    return len(_json_text(value))


def _search_text(*values: Any) -> str:
    return "\n".join(_json_text(value) if not isinstance(value, str) else value for value in values if value is not None)


def _excerpt(text: str, query: str | None = None, limit: int = 500) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    if query:
        pos = clean.lower().find(query.lower())
        if pos > 80:
            clean = clean[max(0, pos - 80) :]
    return _clip_text(clean, limit)


def _result(
    *,
    source_type: str,
    ref_id: str,
    title: str,
    data: Any,
    excerpt_source: str | None = None,
    score: int = 1,
) -> dict[str, Any]:
    text = excerpt_source if excerpt_source is not None else _search_text(data)
    return {
        "source_type": source_type,
        "ref_id": ref_id,
        "title": title,
        "excerpt": _excerpt(text),
        "score": score,
        "data": _safe_data(data),
        "truncated": False,
    }


def _compact_item_to_budget(item: dict[str, Any], max_chars: int) -> dict[str, Any] | None:
    compact: dict[str, Any] = {
        "source_type": str(item.get("source_type") or ""),
        "ref_id": str(item.get("ref_id") or ""),
        "title": _clip_text(str(item.get("title") or ""), 160),
        "excerpt": "",
        "score": item.get("score", 1),
        "data": {"truncated": True},
        "truncated": True,
    }
    if _json_len(compact) > max_chars:
        compact = {
            "source_type": str(item.get("source_type") or ""),
            "ref_id": str(item.get("ref_id") or ""),
            "title": "",
            "excerpt": "",
            "score": item.get("score", 1),
            "truncated": True,
        }
        if _json_len(compact) > max_chars:
            return None

    excerpt = str(item.get("excerpt") or "")
    for excerpt_limit in (500, 250, 120, 60, 24, 0):
        candidate = {**compact, "excerpt": _clip_text(excerpt, excerpt_limit) if excerpt_limit else ""}
        if _json_len(candidate) <= max_chars:
            return candidate
    return compact if _json_len(compact) <= max_chars else None


def _apply_budget(items: list[dict[str, Any]], *, limit: int, max_chars: int) -> dict[str, Any]:
    limit = min(max(1, limit), MAX_EVIDENCE_LIMIT)
    max_chars = min(max(1000, max_chars), MAX_CHAR_BUDGET)
    selected: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for item in items:
        if len(selected) >= limit:
            truncated = True
            break
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        item_len = _json_len(item)
        candidate = item
        if item_len > remaining:
            truncated = True
            compact = _compact_item_to_budget(item, remaining)
            if not compact:
                continue
            candidate = compact
            item_len = _json_len(candidate)
        if item_len > remaining:
            truncated = True
            continue
        selected.append(candidate)
        used += item_len
    return {
        "items": selected,
        "total_candidates": len(items),
        "budget": {
            "limit": limit,
            "max_chars": max_chars,
            "used_chars": used,
            "truncated": truncated or len(selected) < len(items),
        },
    }


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("source_type")), str(item.get("ref_id")))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _matches(query: str, *values: Any) -> tuple[bool, int, str]:
    haystack = _search_text(*values)
    query_l = query.lower().strip()
    haystack_l = haystack.lower()
    if not query_l or query_l not in haystack_l:
        return False, 0, haystack
    return True, max(1, haystack_l.count(query_l)), haystack


def _add_match(
    items: list[dict[str, Any]],
    *,
    query: str,
    source_type: str,
    ref_id: str,
    title: str,
    data: Any,
    text: Any = None,
) -> None:
    ok, score, haystack = _matches(query, title, text, data)
    if ok:
        items.append(
            _result(
                source_type=source_type,
                ref_id=ref_id,
                title=title,
                data=data,
                excerpt_source=haystack,
                score=score,
            )
        )


def exact_retrieve(key_type: str, key: str, *, limit: int = 20, max_chars: int = 20000) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []

    def add(source_type: str, ref_id: str, title: str, data: Any) -> None:
        matches.append(_result(source_type=source_type, ref_id=ref_id, title=title, data=data))

    if key_type == "subject_key":
        for entry in memory_index_repo.list():
            if entry.subject_key == key:
                add("memory_index", entry.index_id, entry.title or entry.memory_id, entry)
                memory = memory_repo.get(entry.memory_id)
                if memory:
                    add("memory", memory.memory_id, memory.title, memory)
        for event in memory_events_repo.list():
            if event.subject_key == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "task_id":
        task = tasks_repo.get(key)
        if task:
            add("task", task.task_id, task.title, task)
        for event in task_events_repo.list():
            if event.task_id == key:
                add("task_event", event.event_id, event.type, event)
        for run in runs_repo.list():
            if run.task_id == key:
                add("run", run.run_id, f"Run {run.status}", run)
        for event in memory_events_repo.list():
            if event.task_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "run_id":
        run = runs_repo.get(key)
        if run:
            add("run", run.run_id, f"Run {run.status}", run)
        for step in run_steps_repo.list():
            if step.run_id == key:
                add("run_step", step.run_step_id, step.step_type, step)
        for log in run_logs_repo.list():
            if log.run_id == key:
                add("run_log", log.log_id, log.level, log)
        for event in memory_events_repo.list():
            if event.run_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "event_id":
        event = memory_events_repo.get(key)
        if event:
            add("memory_event", event.event_id, event.event_type, event)
        task_event = task_events_repo.get(key)
        if task_event:
            add("task_event", task_event.event_id, task_event.type, task_event)
        watchdog_event = watchdog_events_repo.get(key)
        if watchdog_event:
            add("failure", watchdog_event.event_id, watchdog_event.type, watchdog_event)

    elif key_type == "memory_id":
        memory = memory_repo.get(key)
        if memory:
            add("memory", memory.memory_id, memory.title, memory)
        index = memory_index_repo.get(f"memory:{key}")
        if index:
            add("memory_index", index.index_id, index.title or index.memory_id, index)
        for event in memory_events_repo.list():
            if event.memory_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "skill_id":
        skill = skills_repo.get(key)
        if skill:
            add("skill", skill.skill_id, skill.name, skill)
        for step in run_steps_repo.list():
            if step.skill_id == key:
                add("run_step", step.run_step_id, step.step_type, step)
        for event in memory_events_repo.list():
            if event.skill_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "decision_id":
        decision = governor_decisions_repo.get(key)
        if decision:
            add("decision", decision.decision_id, decision.decision, decision)
        for receipt in governor_receipts_repo.list():
            if receipt.decision_id == key:
                add("decision_receipt", receipt.receipt_id, receipt.outcome, receipt)
        for step in run_steps_repo.list():
            if step.decision_id == key:
                add("run_step", step.run_step_id, step.step_type, step)
        for event in memory_events_repo.list():
            if event.decision_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    elif key_type == "failure_id":
        for step in run_steps_repo.list():
            if step.failure_id == key:
                add("run_step", step.run_step_id, step.step_type, step)
        for event in memory_events_repo.list():
            if event.failure_id == key:
                add("memory_event", event.event_id, event.event_type, event)
        watchdog_event = watchdog_events_repo.get(key)
        if watchdog_event:
            add("failure", watchdog_event.event_id, watchdog_event.type, watchdog_event)
        for event in watchdog_events_repo.list():
            if event.normalized_issue_signature == key:
                add("failure", event.event_id, event.type, event)

    elif key_type == "conversation_id":
        conversation = conversations_repo.get(key)
        if conversation:
            add("conversation", conversation.conversation_id, conversation.title, conversation)
        for message in conversation_messages_repo.list():
            if message.conversation_id == key:
                add("conversation_message", message.message_id, message.role, message)
        for memory in memory_repo.list():
            if memory.conversation_id == key:
                add("memory", memory.memory_id, memory.title, memory)
        for event in memory_events_repo.list():
            if event.conversation_id == key:
                add("memory_event", event.event_id, event.event_type, event)

    matches = _dedupe(matches)
    return {
        "key_type": key_type,
        "key": key,
        "layer": "exact",
        **_apply_budget(matches, limit=limit, max_chars=max_chars),
    }


def native_evidence_search(
    query: str,
    *,
    sources: list[str] | None = None,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    max_chars: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any]:
    selected = set(sources or NATIVE_EVIDENCE_SOURCES)
    selected = {source for source in selected if source in NATIVE_EVIDENCE_SOURCES}
    items: list[dict[str, Any]] = []

    def enabled(*names: str) -> bool:
        return any(name in selected for name in names)

    if enabled("workspace", "evidence"):
        for artifact in file_artifacts_repo.list():
            _add_match(
                items,
                query=query,
                source_type="workspace",
                ref_id=artifact.file_id,
                title=artifact.name,
                data=artifact,
                text=[artifact.path, artifact.description, artifact.tags],
            )

    if enabled("raw_logs", "run_logs"):
        for log in run_logs_repo.list():
            _add_match(
                items,
                query=query,
                source_type="run_log",
                ref_id=log.log_id,
                title=f"{log.level} run log",
                data=log,
                text=[log.message, log.meta],
            )

    if enabled("conversation_logs"):
        for conversation in conversations_repo.list():
            _add_match(
                items,
                query=query,
                source_type="conversation",
                ref_id=conversation.conversation_id,
                title=conversation.title,
                data=conversation,
            )
        for message in conversation_messages_repo.list():
            _add_match(
                items,
                query=query,
                source_type="conversation_message",
                ref_id=message.message_id,
                title=f"{message.role} message",
                data=message,
                text=message.content,
            )

    if enabled("task_logs"):
        for task in tasks_repo.list():
            _add_match(
                items,
                query=query,
                source_type="task",
                ref_id=task.task_id,
                title=task.title,
                data=task,
                text=[task.description, task.last_error, task.result_summary, task.result_payload],
            )
        for event in task_events_repo.list():
            _add_match(
                items,
                query=query,
                source_type="task_event",
                ref_id=event.event_id,
                title=event.type,
                data=event,
                text=[event.message, event.payload],
            )

    if enabled("memory_events"):
        for event in memory_events_repo.list():
            _add_match(
                items,
                query=query,
                source_type="memory_event",
                ref_id=event.event_id,
                title=event.event_type,
                data=event,
                text=[event.subject_key, event.content_json, event.value_json, event.metadata],
            )

    if enabled("evidence"):
        for event in memory_events_repo.list():
            if event.evidence_refs:
                _add_match(
                    items,
                    query=query,
                    source_type="evidence",
                    ref_id=event.event_id,
                    title=f"Memory evidence refs for {event.event_type}",
                    data={"event_id": event.event_id, "evidence_refs": event.evidence_refs},
                    text=event.evidence_refs,
                )
        for step in run_steps_repo.list():
            if step.evidence_refs:
                _add_match(
                    items,
                    query=query,
                    source_type="evidence",
                    ref_id=step.run_step_id,
                    title=f"Run step evidence refs for {step.step_type}",
                    data={"run_step_id": step.run_step_id, "evidence_refs": step.evidence_refs},
                    text=step.evidence_refs,
                )
        for suggestion in advisor_suggestions_repo.list():
            if suggestion.evidence_refs:
                _add_match(
                    items,
                    query=query,
                    source_type="evidence",
                    ref_id=suggestion.suggestion_id,
                    title=suggestion.title,
                    data=suggestion,
                    text=suggestion.evidence_refs,
                )

    if enabled("summaries"):
        for task in tasks_repo.list():
            if task.result_summary:
                _add_match(
                    items,
                    query=query,
                    source_type="summary",
                    ref_id=task.task_id,
                    title=f"Task summary: {task.title}",
                    data=task,
                    text=task.result_summary,
                )
        for run in runs_repo.list():
            if run.output_excerpt or run.callback_summary:
                _add_match(
                    items,
                    query=query,
                    source_type="summary",
                    ref_id=run.run_id,
                    title=f"Run summary: {run.status}",
                    data=run,
                    text=[run.output_excerpt, run.callback_summary],
                )
        for report in reports_repo.list():
            _add_match(
                items,
                query=query,
                source_type="summary",
                ref_id=report.report_id,
                title=report.title,
                data=report,
                text=report.content,
            )
        for master in master_tasks_repo.list():
            if master.final_summary:
                _add_match(
                    items,
                    query=query,
                    source_type="summary",
                    ref_id=master.master_task_id,
                    title="Kanaloa orchestration summary",
                    data=master,
                    text=master.final_summary,
                )

    if enabled("skills"):
        for skill in skills_repo.list():
            _add_match(
                items,
                query=query,
                source_type="skill",
                ref_id=skill.skill_id,
                title=skill.name,
                data=skill,
                text=[skill.description, skill.category, skill.input_schema, skill.output_schema],
            )

    if enabled("decisions"):
        for decision in governor_decisions_repo.list():
            _add_match(
                items,
                query=query,
                source_type="decision",
                ref_id=decision.decision_id,
                title=decision.decision,
                data=decision,
                text=[decision.reason, decision.policy_snapshot, decision.gates_failed, decision.gates_passed],
            )
        for receipt in governor_receipts_repo.list():
            _add_match(
                items,
                query=query,
                source_type="decision_receipt",
                ref_id=receipt.receipt_id,
                title=receipt.outcome,
                data=receipt,
                text=[receipt.result_summary, receipt.error],
            )

    if enabled("failures", "raw_logs"):
        for event in watchdog_events_repo.list():
            _add_match(
                items,
                query=query,
                source_type="failure",
                ref_id=event.event_id,
                title=event.type,
                data=event,
                text=[event.message, event.raw_error, event.recovery_hint, event.normalized_issue_signature],
            )
        for task in tasks_repo.list():
            if task.status.value == "failed" or task.last_error:
                _add_match(
                    items,
                    query=query,
                    source_type="failure",
                    ref_id=task.task_id,
                    title=f"Failed task: {task.title}",
                    data=task,
                    text=[task.last_error, task.description],
                )
        for run in runs_repo.list():
            if run.status == "failed" or run.error:
                _add_match(
                    items,
                    query=query,
                    source_type="failure",
                    ref_id=run.run_id,
                    title="Failed run",
                    data=run,
                    text=[run.error, run.output_excerpt, run.callback_summary],
                )
        for step in run_steps_repo.list():
            if step.status == "failed" or step.failure_id:
                _add_match(
                    items,
                    query=query,
                    source_type="failure",
                    ref_id=step.run_step_id,
                    title=f"Run step failure: {step.step_type}",
                    data=step,
                    text=[step.failure_id, step.metadata],
                )

    items.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("source_type")), str(item.get("ref_id"))))
    return {
        "query": query,
        "layer": "native_evidence_search",
        "sources": sorted(selected),
        **_apply_budget(_dedupe(items), limit=limit, max_chars=max_chars),
    }


def _tail(items: list[Any], *, key: Callable[[Any], Any], limit: int) -> list[Any]:
    return sorted(items, key=key)[-limit:]


def _build_query_from_context(task_id: str | None, run_id: str | None, conversation_id: str | None) -> str:
    parts: list[str] = []
    if task_id:
        task = tasks_repo.get(task_id)
        if task:
            parts.extend([task.title, task.description or "", task.result_summary or "", task.last_error or ""])
    if run_id:
        run = runs_repo.get(run_id)
        if run:
            parts.extend([run.output_excerpt or "", run.error or "", _json_text(run.callback_summary or {})])
    if conversation_id:
        conversation = conversations_repo.get(conversation_id)
        if conversation:
            parts.append(conversation.title)
        messages = [message for message in conversation_messages_repo.list() if message.conversation_id == conversation_id]
        for message in _tail(messages, key=lambda item: item.created_at, limit=3):
            parts.append(message.content)
    return " ".join(part for part in parts if part).strip()


def build_runtime_memory_context(
    *,
    query: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    conversation_id: str | None = None,
    evidence_limit: int = 8,
    max_chars: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any]:
    snapshot = rebuild_active_snapshot()
    run = runs_repo.get(run_id) if run_id else None
    if run and not task_id:
        task_id = run.task_id

    current: dict[str, Any] = {}
    if task_id:
        task = tasks_repo.get(task_id)
        if task:
            current["task"] = _safe_data(task)
        task_events = [event for event in task_events_repo.list() if event.task_id == task_id]
        current["task_events_tail"] = [_safe_data(event) for event in _tail(task_events, key=lambda item: item.created_at, limit=5)]

    if run_id:
        if run:
            current["run"] = _safe_data(run)
        run_steps = [step for step in run_steps_repo.list() if step.run_id == run_id]
        run_logs = [log for log in run_logs_repo.list() if log.run_id == run_id]
        current["run_steps"] = [_safe_data(step) for step in sorted(run_steps, key=lambda item: item.sequence)[:10]]
        current["run_logs_tail"] = [_safe_data(log) for log in _tail(run_logs, key=lambda item: item.seq, limit=5)]

    if conversation_id:
        conversation = conversations_repo.get(conversation_id)
        if conversation:
            current["conversation"] = _safe_data(conversation)
        messages = [message for message in conversation_messages_repo.list() if message.conversation_id == conversation_id]
        current["conversation_messages_tail"] = [
            _safe_data(message) for message in _tail(messages, key=lambda item: item.created_at, limit=5)
        ]

    search_query = (query or _build_query_from_context(task_id, run_id, conversation_id)).strip()
    evidence = (
        native_evidence_search(search_query, limit=evidence_limit, max_chars=max_chars)
        if search_query
        else {"items": [], "total_candidates": 0, "budget": {"limit": evidence_limit, "max_chars": max_chars, "used_chars": 0, "truncated": False}}
    )

    active_snapshot = active_memory_snapshots_repo.get(snapshot.snapshot_id) or snapshot
    return {
        "runtime_policy": {
            "prompt_sources": ["active_snapshot", "relevant_evidence", "current_run_context"],
            "ledger_policy": "Memory Ledger is audit data and is not injected directly.",
        },
        "active_snapshot": _safe_data(active_snapshot),
        "relevant_evidence": evidence["items"],
        "current_run_context": current,
        "budget": {
            "evidence_limit": evidence_limit,
            "max_chars": max_chars,
            "evidence_used_chars": evidence["budget"]["used_chars"],
            "evidence_truncated": evidence["budget"]["truncated"],
        },
    }

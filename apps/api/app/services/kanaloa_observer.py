"""
Read-only observation helpers for orchestrator (tasks, events, run logs).

Strips common secret patterns from summaries — never echo raw .env / keys.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import TaskStatus
from ..store.run_log_queries import list_logs_for_run
from ..store.repositories import run_logs_repo, runs_repo, task_events_repo, tasks_repo

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END"),
    re.compile(r"(?i)\.env\b[^\n]*"),
]


def sanitize_text(text: str | None, max_len: int = 2000) -> str | None:
    if not text:
        return None
    s = text[: max_len * 2]
    for pat in _SECRET_PATTERNS:
        s = pat.sub("[redacted]", s)
    return s[:max_len]


def observe_platform_task(task_id: str) -> dict[str, Any]:
    t = tasks_repo.get(task_id)
    if not t:
        return {"ok": False, "error": "task_not_found"}
    return {
        "ok": True,
        "task_id": task_id,
        "status": t.status.value,
        "assigned_agent_id": t.assigned_agent_id,
        "last_run_id": t.last_run_id,
        "last_error": sanitize_text(t.last_error, 800),
        "result_summary": sanitize_text(t.result_summary, 1200),
    }


def observe_task_events(task_id: str, *, limit: int = 40) -> dict[str, Any]:
    if not tasks_repo.get(task_id):
        return {"ok": False, "error": "task_not_found"}
    evs = [e.model_dump() for e in task_events_repo.list() if e.task_id == task_id]
    evs.sort(key=lambda x: x.get("created_at") or "")
    slim: list[dict[str, Any]] = []
    for e in evs[-limit:]:
        slim.append(
            {
                "type": e.get("type"),
                "message": sanitize_text(e.get("message"), 500),
                "created_at": e.get("created_at"),
                "payload": _sanitize_payload(e.get("payload")),
            }
        )
    return {"ok": True, "task_id": task_id, "events": slim}


def _sanitize_payload(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in list(payload.items())[:24]:
            if isinstance(v, str):
                out[str(k)] = sanitize_text(v, 400)
            else:
                out[str(k)] = v
        return out
    return payload


def observe_run_logs(run_id: str, *, limit: int = 60) -> dict[str, Any]:
    run = runs_repo.get(run_id)
    if not run:
        return {"ok": False, "error": "run_not_found"}
    lines, _total = list_logs_for_run(run_id, tail=limit)
    msgs: list[str] = []
    for ln in lines:
        msgs.append(sanitize_text(ln.message, 400) or "")
    return {
        "ok": True,
        "run_id": run_id,
        "run_status": run.status,
        "error": sanitize_text(run.error, 600),
        "output_excerpt": sanitize_text(run.output_excerpt, 1200),
        "log_messages": [m for m in msgs if m],
    }


def terminal_status(status: TaskStatus) -> bool:
    return status in {
        TaskStatus.succeeded,
        TaskStatus.failed,
        TaskStatus.cancelled,
        TaskStatus.expired,
    }


def summarize_observation_for_subtask(task_id: str | None, run_id: str | None) -> str:
    parts: list[str] = []
    if task_id:
        o = observe_platform_task(task_id)
        if o.get("ok"):
            parts.append(f"task_status={o.get('status')}")
            if o.get("last_error"):
                parts.append(f"err={o.get('last_error')}")
    if run_id:
        rl = observe_run_logs(run_id)
        if rl.get("ok") and rl.get("log_messages"):
            parts.append("logs=" + "; ".join(rl["log_messages"][:4]))
    return "; ".join(parts) if parts else "no_observation"

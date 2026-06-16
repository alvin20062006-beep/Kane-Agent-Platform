"""Resolve platform task → orchestrator master/subtask context (read-only)."""

from __future__ import annotations

from typing import Any

from ..store.repositories import master_tasks_repo

_SUBTASK_TERMINAL = frozenset({"completed", "failed", "skipped"})
_MASTER_TERMINAL = frozenset({"completed", "failed", "cancelled"})


def find_master_context_for_platform_task(platform_task_id: str) -> dict[str, Any] | None:
    tid = platform_task_id.strip()
    if not tid:
        return None
    for master in master_tasks_repo.list():
        for sub in master.subtasks:
            if sub.platform_task_id != tid:
                continue
            total = len(master.subtasks)
            done = sum(1 for s in master.subtasks if s.status in _SUBTASK_TERMINAL)
            return {
                "master_task_id": master.master_task_id,
                "subtask_id": sub.subtask_id,
                "subtask_title": sub.title,
                "subtask_status": sub.status,
                "master_status": master.status,
                "user_instruction": (master.user_instruction or "")[:240],
                "subtasks_done": done,
                "subtasks_total": total,
                "master_active": master.status not in _MASTER_TERMINAL,
            }
    return None

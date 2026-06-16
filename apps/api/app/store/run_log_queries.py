"""Filtered run-log reads (Phase 5). Centralizes tail windows over file-backed store."""

from __future__ import annotations

from ..models import RunLogLine
from .repositories import run_logs_repo


def list_logs_for_run(run_id: str, *, tail: int | None = None) -> tuple[list[RunLogLine], int]:
    logs = [line for line in run_logs_repo.list() if line.run_id == run_id]
    logs.sort(key=lambda x: x.seq)
    total = len(logs)
    if tail and total > tail:
        logs = logs[-tail:]
    return logs, total


def list_logs_for_runs(run_ids: set[str], *, tail: int | None = None) -> tuple[list[RunLogLine], int]:
    if not run_ids:
        return [], 0
    logs = [line for line in run_logs_repo.list() if line.run_id in run_ids]
    logs.sort(key=lambda x: (x.run_id, x.seq))
    total = len(logs)
    if tail and total > tail:
        logs = logs[-tail:]
    return logs, total


def list_logs_for_run_since(run_id: str, since_seq: int) -> list[RunLogLine]:
    logs = [line for line in run_logs_repo.list() if line.run_id == run_id and line.seq > since_seq]
    logs.sort(key=lambda x: x.seq)
    return logs

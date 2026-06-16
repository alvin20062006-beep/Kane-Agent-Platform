"""Lightweight API startup phase timing (Phase 4). Logs to logger octopus.startup."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("octopus.startup")

_t0 = time.perf_counter()
_last = _t0
_phases: list[dict[str, Any]] = []


def _logging_enabled() -> bool:
    raw = (os.getenv("OCTOPUS_STARTUP_LOG") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def mark(phase: str) -> None:
    global _last
    now = time.perf_counter()
    delta_ms = round((now - _last) * 1000, 1)
    total_ms = round((now - _t0) * 1000, 1)
    _phases.append({"phase": phase, "delta_ms": delta_ms, "total_ms": total_ms})
    if _logging_enabled():
        logger.info("startup %-28s +%7.1fms  (total %7.1fms)", phase, delta_ms, total_ms)
    _last = now


def summary() -> dict[str, Any]:
    total_ms = round((time.perf_counter() - _t0) * 1000, 1) if _phases else 0.0
    return {"total_ms": total_ms, "phases": list(_phases)}

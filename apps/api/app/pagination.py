"""Shared list pagination/limit helpers (Phase 5: prevent unbounded responses)."""

from __future__ import annotations

from typing import Any, Sequence

# Generous defaults: large enough to keep current demos/tests intact,
# small enough to prevent unbounded payloads as stored data grows.
DEFAULT_LIST_LIMIT = 200
MAX_LIST_LIMIT = 1000

DEFAULT_TIMELINE_EVENTS_LIMIT = 200
DEFAULT_TIMELINE_LOGS_LIMIT = 500
MAX_TIMELINE_EVENTS_LIMIT = 5000
MAX_TIMELINE_LOGS_LIMIT = 10000

MEMORY_SEARCH_MAX_SCAN = 400
MEMORY_SEARCH_MAX_HITS = 8


def clamp_limit(limit: int | None, default_limit: int = DEFAULT_LIST_LIMIT, max_limit: int = MAX_LIST_LIMIT) -> int:
    if limit is None:
        return default_limit
    if limit < 1:
        return 1
    return min(limit, max_limit)


def clamp_offset(offset: int | None) -> int:
    if offset is None or offset < 0:
        return 0
    return offset


def paginate(
    items: Sequence[Any],
    limit: int | None,
    offset: int | None = 0,
    default_limit: int = DEFAULT_LIST_LIMIT,
    max_limit: int = MAX_LIST_LIMIT,
) -> tuple[list[Any], dict[str, int]]:
    """Return (window, meta). Caller is responsible for ordering before paginating."""
    eff_limit = clamp_limit(limit, default_limit, max_limit)
    eff_offset = clamp_offset(offset)
    total = len(items)
    window = list(items[eff_offset : eff_offset + eff_limit])
    return window, {"total": total, "limit": eff_limit, "offset": eff_offset}

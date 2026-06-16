"""Legacy `/v1/*` routes: same persistence as unprefixed platform routes (not in-memory mocks)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..models import ListResponse
from ..pagination import paginate
from ..services.watchdog_metrics import build_watchdog_status
from ..version import PLATFORM_VERSION
from ..store.repositories import accounts_repo, agents_repo, memory_repo, skills_repo, tasks_repo

router = APIRouter(tags=["resources"])

LEGACY_V1_NOTE = (
    "Legacy /v1/* list paths mirror the file/Postgres-backed store used by /agents, /tasks, … "
    "Prefer unprefixed routes for new integrations."
)


@router.get("/agents", response_model=ListResponse)
def list_agents():
    return ListResponse(version=PLATFORM_VERSION, note=LEGACY_V1_NOTE, items=agents_repo.list())


@router.get("/tasks", response_model=ListResponse)
def list_tasks(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = tasks_repo.list()
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=LEGACY_V1_NOTE, items=window, **meta)


@router.get("/skills", response_model=ListResponse)
def list_skills():
    items = [s for s in skills_repo.list() if skill_is_user_visible(s)]
    return ListResponse(version=PLATFORM_VERSION, note=LEGACY_V1_NOTE, items=items)


@router.get("/accounts", response_model=ListResponse)
def list_accounts():
    return ListResponse(version=PLATFORM_VERSION, note=LEGACY_V1_NOTE, items=accounts_repo.list())


@router.get("/memory", response_model=ListResponse)
def list_memory(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = memory_repo.list()
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=LEGACY_V1_NOTE, items=window, **meta)


@router.get("/watchdog")
def get_watchdog():
    st = build_watchdog_status()
    return {
        "version": PLATFORM_VERSION,
        "note": LEGACY_V1_NOTE,
        "data": st,
    }

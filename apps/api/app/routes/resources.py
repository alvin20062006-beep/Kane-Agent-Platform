"""Legacy `/v1/*` routes: same persistence as unprefixed platform routes (not in-memory mocks)."""

from __future__ import annotations

from fastapi import APIRouter

from ..models import ListResponse
from ..services.watchdog_metrics import build_watchdog_status
from ..skill_visibility import skill_is_user_visible
from ..store.repositories import accounts_repo, agents_repo, memory_repo, skills_repo, tasks_repo

router = APIRouter(tags=["resources"])

LEGACY_V1_NOTE = (
    "Legacy /v1/* list paths mirror the file/Postgres-backed store used by /agents, /tasks, … "
    "Prefer unprefixed routes for new integrations."
)


@router.get("/agents", response_model=ListResponse)
def list_agents():
    return ListResponse(is_mock=False, beta=True, note=LEGACY_V1_NOTE, items=agents_repo.list())


@router.get("/tasks", response_model=ListResponse)
def list_tasks():
    return ListResponse(is_mock=False, beta=True, note=LEGACY_V1_NOTE, items=tasks_repo.list())


@router.get("/skills", response_model=ListResponse)
def list_skills():
    items = [s for s in skills_repo.list() if skill_is_user_visible(s)]
    return ListResponse(is_mock=False, beta=True, note=LEGACY_V1_NOTE, items=items)


@router.get("/accounts", response_model=ListResponse)
def list_accounts():
    return ListResponse(is_mock=False, beta=True, note=LEGACY_V1_NOTE, items=accounts_repo.list())


@router.get("/memory", response_model=ListResponse)
def list_memory():
    return ListResponse(is_mock=False, beta=True, note=LEGACY_V1_NOTE, items=memory_repo.list())


@router.get("/watchdog")
def get_watchdog():
    st = build_watchdog_status()
    return {
        "is_mock": False,
        "beta": True,
        "note": LEGACY_V1_NOTE,
        "data": st,
    }

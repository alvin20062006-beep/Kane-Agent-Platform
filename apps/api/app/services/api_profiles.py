from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import AgentApiBinding, AgentApiProfile, AgentApiProfileUpsertBody
from ..store.repositories import agents_repo, api_bindings_repo, api_profiles_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _mask_profile(p: AgentApiProfile) -> dict[str, Any]:
    d = p.model_dump()
    if d.get("api_key"):
        d["api_key"] = "********"
    else:
        d["api_key"] = None
    return d


def list_profiles() -> list[dict[str, Any]]:
    items = api_profiles_repo.list()
    items.sort(key=lambda x: (not x.is_default, x.updated_at or x.created_at), reverse=True)
    return [_mask_profile(p) for p in items]


def upsert_profile(body: AgentApiProfileUpsertBody) -> dict[str, Any]:
    now = _now_iso()
    if body.profile_id:
        existing = api_profiles_repo.get(body.profile_id)
        if not existing:
            raise HTTPException(status_code=404, detail="profile_not_found")
        api_key = body.api_key if body.api_key is not None and body.api_key.strip() else existing.api_key
        updated = existing.model_copy(
            update={
                "name": body.name,
                "provider": body.provider,
                "base_url": body.base_url.rstrip("/"),
                "model": body.model,
                "api_key": api_key,
                "updated_at": now,
                "is_default": bool(body.is_default),
            }
        )
        if updated.is_default:
            # unset other defaults
            for p in api_profiles_repo.list():
                if p.profile_id != updated.profile_id and p.is_default:
                    api_profiles_repo.upsert(p.model_copy(update={"is_default": False, "updated_at": now}))
        api_profiles_repo.upsert(updated)
        return _mask_profile(updated)

    profile = AgentApiProfile(
        profile_id=new_id("apip"),
        name=body.name,
        provider=body.provider,
        base_url=body.base_url.rstrip("/"),
        model=body.model,
        api_key=body.api_key.strip() if body.api_key else None,
        created_at=now,
        updated_at=now,
        is_default=bool(body.is_default),
    )
    if profile.is_default:
        for p in api_profiles_repo.list():
            if p.is_default:
                api_profiles_repo.upsert(p.model_copy(update={"is_default": False, "updated_at": now}))
    api_profiles_repo.upsert(profile)
    return _mask_profile(profile)


def get_profile(profile_id: str) -> dict[str, Any]:
    p = api_profiles_repo.get(profile_id)
    if not p:
        raise HTTPException(status_code=404, detail="profile_not_found")
    return _mask_profile(p)


def bind_agent(agent_id: str, profile_id: str) -> AgentApiBinding:
    if not agents_repo.get(agent_id):
        raise HTTPException(status_code=404, detail="agent_not_found")
    if not api_profiles_repo.get(profile_id):
        raise HTTPException(status_code=404, detail="profile_not_found")
    now = _now_iso()
    # upsert by agent_id
    existing = next((b for b in api_bindings_repo.list() if b.agent_id == agent_id), None)
    if existing:
        updated = existing.model_copy(update={"profile_id": profile_id, "updated_at": now})
        api_bindings_repo.upsert(updated)
        return updated
    b = AgentApiBinding(binding_id=new_id("apib"), agent_id=agent_id, profile_id=profile_id, created_at=now, updated_at=now)
    api_bindings_repo.upsert(b)
    return b


def get_agent_binding(agent_id: str) -> dict[str, Any]:
    b = next((x for x in api_bindings_repo.list() if x.agent_id == agent_id), None)
    if not b:
        return {"agent_id": agent_id, "binding": None, "profile": None}
    p = api_profiles_repo.get(b.profile_id)
    return {"agent_id": agent_id, "binding": b, "profile": _mask_profile(p) if p else None}


def resolve_profile_for_agent(agent_id: str) -> AgentApiProfile | None:
    b = next((x for x in api_bindings_repo.list() if x.agent_id == agent_id), None)
    if b:
        return api_profiles_repo.get(b.profile_id)
    # fallback default
    return next((p for p in api_profiles_repo.list() if p.is_default), None)


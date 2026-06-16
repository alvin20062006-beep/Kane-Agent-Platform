"""
Profile-based permission gate for Kanaloa (P2).

- owner: self-hosted full orchestrator; external execute is allowed without OCTOPUS_KANALOA_ADAPTER_EXECUTE.
- safe: stricter; external execute also requires is_adapter_execute_enabled().
- readonly: read/list/status only; mutations return 403.

Override scopes with OCTOPUS_KANALOA_SCOPES=comma,list (tests / advanced ops).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from ..models import Agent
from ..settings_env import get_kane_permission_profile
from .kanaloa_platform import is_adapter_execute_enabled, scopes_for_permission_profile


@dataclass(frozen=True)
class Principal:
    scopes: frozenset[str]
    profile: str  # owner | safe | readonly


def get_kanaloa_principal() -> Principal:
    profile = get_kane_permission_profile()
    raw = (os.getenv("OCTOPUS_KANALOA_SCOPES") or "").strip()
    if raw:
        scopes = frozenset(s.strip() for s in raw.split(",") if s.strip())
        return Principal(scopes=scopes, profile=profile)
    return Principal(
        scopes=frozenset(scopes_for_permission_profile(profile)),
        profile=profile,
    )


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise HTTPException(
            status_code=403,
            detail={"error": "permission_denied", "scope": scope, "profile": principal.profile},
        )


def workspace_in_allowlist(workspace: str | None) -> tuple[bool, str | None]:
    """If OCTOPUS_KANALOA_WORKSPACE_ALLOWLIST is set, workspace must fall under a listed root."""
    raw = (os.getenv("OCTOPUS_KANALOA_WORKSPACE_ALLOWLIST") or "").strip()
    if not workspace or not raw:
        return True, None
    from pathlib import Path

    try:
        wp = Path(workspace).expanduser().resolve()
    except Exception:  # noqa: BLE001
        return False, "invalid_workspace_path"
    roots = [Path(p.strip()).expanduser().resolve() for p in raw.split(",") if p.strip()]
    for r in roots:
        try:
            wp.relative_to(r)
            return True, None
        except ValueError:
            continue
    return False, "workspace_not_in_allowlist"


def assert_can_execute_external(
    principal: Principal,
    agent: Agent,
    workspace: str | None,
) -> None:
    """Gate external-agent execute / run_task — audit elsewhere; do not blanket-deny owner."""
    if principal.profile == "readonly":
        raise HTTPException(
            status_code=403,
            detail={"error": "readonly_profile", "message": "Mutation disabled in readonly profile"},
        )
    require_scope(principal, "agents.dispatch")
    require_scope(principal, "adapters.dispatch")
    if not agent.enabled:
        raise HTTPException(status_code=400, detail="agent_disabled")
    if agent.type != "external":
        raise HTTPException(status_code=400, detail="execute_external_requires_external_agent")
    if principal.profile == "safe" and not is_adapter_execute_enabled():
        raise HTTPException(
            status_code=403,
            detail="execute_requires_OCTOPUS_KANALOA_ADAPTER_EXECUTE_in_safe_profile",
        )
    ok, err = workspace_in_allowlist(workspace)
    if not ok:
        raise HTTPException(status_code=403, detail=err or "workspace_forbidden")


def safe_detail(e: HTTPException) -> dict[str, Any]:
    d = e.detail
    if isinstance(d, dict):
        return d
    return {"error": str(d)}

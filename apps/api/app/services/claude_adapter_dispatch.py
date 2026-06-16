"""
Claude Code adapter HTTP surface: delegates to Kanaloa Action Gateway + task lifecycle.

dry_run: creates assigned task, does not queue worker run.
execute: permission gate + create + assign + run_task.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..models import ClaudeAdapterDispatchBody
from .kanaloa_actions import create_agent_task, first_enabled_claude_agent_id
from .kanaloa_platform import build_adapters_status_payload
from .permission_gate import get_kanaloa_principal, require_scope, workspace_in_allowlist


def dispatch_claude(body: ClaudeAdapterDispatchBody) -> dict[str, Any]:
    mode = (body.mode or "dry_run").strip().lower()
    if mode not in {"dry_run", "execute"}:
        raise HTTPException(status_code=400, detail="invalid_mode")

    allow_ws, ws_err = workspace_in_allowlist(getattr(body, "workspace", None))
    if not allow_ws:
        raise HTTPException(status_code=403, detail=ws_err or "workspace_forbidden")

    if getattr(body, "workspace", None):
        p = Path(body.workspace).expanduser()
        if not p.exists():
            return {
                "ok": False,
                "mode": mode,
                "error": "workspace_path_missing",
                "claude_adapter_status": build_adapters_status_payload()["claude_code"],
            }

    st = build_adapters_status_payload()["claude_code"]
    agent_id = first_enabled_claude_agent_id()
    if not agent_id:
        return {
            "ok": False,
            "mode": mode,
            "error": "no_enabled_claude_code_agent",
            "claude_adapter_status": st,
        }

    principal = get_kanaloa_principal()
    instruction = (body.task or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="task_required")

    if mode == "dry_run":
        require_scope(principal, "tasks.create")
        return create_agent_task(
            principal,
            agent_id=agent_id,
            instruction=instruction,
            mode="dry_run",
            workspace=body.workspace,
        )

    require_scope(principal, "adapters.dispatch")
    return create_agent_task(
        principal,
        agent_id=agent_id,
        instruction=instruction,
        mode="execute",
        workspace=body.workspace,
    )

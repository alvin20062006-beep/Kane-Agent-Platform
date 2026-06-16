"""
Map orchestrator subtask kinds to concrete agents using registry + live adapter status.
Never fabricates Cursor connectivity — consults build_adapters_status_payload().
"""

from __future__ import annotations

from typing import Any

from ..store.repositories import agents_repo
from .kanaloa_platform import build_adapters_status_payload


def _enabled_external_by_adapter(adapter_id: str) -> str | None:
    for a in agents_repo.list():
        if not a.enabled or a.type != "external":
            continue
        if (a.adapter_id or "") == adapter_id:
            return a.agent_id
    return None


def adapter_health(adapter_key: str) -> dict[str, Any]:
    payload = build_adapters_status_payload()
    block = payload.get(adapter_key) or {}
    return {
        "health": block.get("health"),
        "configured": block.get("configured"),
        "available": block.get("available"),
        "details": block.get("details"),
    }


def select_agent_for_kind(kind: str) -> tuple[str | None, str | None, dict[str, Any]]:
    """
    Returns (agent_id, adapter_id, evidence).

    Preference for code paths: claude_code > cursor_cli (only if adapter reports usable)
    > openclaw_http > local_script.
    """
    kind_n = (kind or "unknown").strip().lower()
    adapters = build_adapters_status_payload()
    evidence: dict[str, Any] = {"kind": kind_n, "adapter_resolution": []}

    def pick_first(mapping: list[tuple[str, str]]) -> tuple[str | None, str | None]:
        for adapter_id, adapter_key in mapping:
            st = adapters.get(adapter_key) or {}
            health = str(st.get("health") or "")
            agent_id = _enabled_external_by_adapter(adapter_id)
            evidence["adapter_resolution"].append(
                {
                    "adapter_id": adapter_id,
                    "health": health,
                    "enabled_agent": agent_id,
                }
            )
            if not agent_id:
                continue
            if adapter_id == "cursor_cli":
                if health not in {"ok"}:
                    continue
            return agent_id, adapter_id
        return None, None

    if kind_n in {"code_audit", "code_fix", "frontend_check"}:
        aid, ad = pick_first(
            [
                ("claude_code", "claude_code"),
                ("codex_cli", "codex_cli"),
                ("cursor_cli", "cursor"),
                ("openclaw_http", "openclaw_http"),
                ("local_script", "local_bridge"),
            ]
        )
        if aid:
            return aid, ad, evidence
        # Honest failure
        cc = adapter_health("claude_code")
        return None, None, {**evidence, "reason": "no_enabled_agent_for_code_task", "claude_code": cc}

    if kind_n == "repo_status":
        aid, ad = pick_first([("local_script", "local_bridge"), ("claude_code", "claude_code")])
        if aid:
            return aid, ad, evidence
        return None, None, {**evidence, "reason": "no_agent_for_repo_status"}

    if kind_n == "external_http_task":
        aid, ad = pick_first([("openclaw_http", "openclaw_http")])
        if aid:
            return aid, ad, evidence
        oh = adapter_health("openclaw_http")
        return None, None, {**evidence, "reason": "openclaw_unavailable", "openclaw_http": oh}

    if kind_n == "cursor_task":
        cur = adapters.get("cursor") or {}
        if str(cur.get("health") or "") != "ok":
            return None, None, {**evidence, "reason": "cursor_not_available", "cursor": cur}
        aid = _enabled_external_by_adapter("cursor_cli")
        if aid:
            return aid, "cursor_cli", evidence
        return None, None, {**evidence, "reason": "no_enabled_cursor_agent", "cursor": cur}

    if kind_n == "verification":
        aid, ad = pick_first([("local_script", "local_bridge"), ("claude_code", "claude_code")])
        if aid:
            return aid, ad, evidence
        return None, None, {**evidence, "reason": "no_agent_for_verification"}

    if kind_n == "summarize":
        built = _enabled_external_by_adapter("claude_code")
        if built:
            return built, "claude_code", evidence
        return None, None, {**evidence, "reason": "summarize_prefers_claude_missing"}

    # unknown → try Claude then local_script
    aid, ad = pick_first([("claude_code", "claude_code"), ("local_script", "local_bridge")])
    if aid:
        return aid, ad, evidence
    return None, None, {**evidence, "reason": "unknown_kind_no_agent"}

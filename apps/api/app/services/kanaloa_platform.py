"""
Kanaloa orchestrator: permissions, capability payloads, adapter/agent registry views.

Authoritative connectivity signals come from Local Bridge HTTP probes + agent store,
never from LLM guessing.
"""
from __future__ import annotations

import json
import os
import shutil
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..settings_env import (
    get_api_public_url,
    get_kane_permission_profile,
    get_local_bridge_url,
    get_openclaw_webhook_url,
    get_persistence_backend,
)
from ..store.repositories import agents_repo, skills_repo
from .llm_client import is_llm_configured
from .watchdog_metrics import probe_local_bridge_detailed

APP_NAME = "Kane AI Agent Platform"
KANALOA_AGENT_ID = "octopus_builtin"

# Owner / superuser profile — private deployment full orchestrator (default product mode).
KANALOA_OWNER_SCOPES: list[str] = [
    "system.read_capabilities",
    "agents.list",
    "agents.read",
    "agents.dispatch",
    "agents.manage",
    "tools.list",
    "tools.call",
    "adapters.list",
    "adapters.status",
    "adapters.dispatch",
    "adapters.execute",
    "mcp.list",
    "mcp.call",
    "workspace.list",
    "workspace.read",
    "workspace.write",
    "workspace.patch",
    "workspace.delete_if_requested",
    "shell.exec_via_adapter",
    "tasks.create",
    "tasks.read",
    "tasks.cancel",
    "tasks.run",
    "audit.read",
    "audit.write",
    "memory.read",
    "memory.write",
    "git.status",
    "git.diff",
    "git.commit_if_requested",
]

# Shared / demo deployments — narrower mutate surface.
KANALOA_SAFE_SCOPES: list[str] = [
    "system.read_capabilities",
    "agents.list",
    "agents.read",
    "agents.dispatch",
    "tools.list",
    "tools.call",
    "adapters.list",
    "adapters.status",
    "adapters.dispatch",
    "mcp.list",
    "workspace.list",
    "workspace.read",
    "tasks.create",
    "tasks.read",
    "tasks.cancel",
    "tasks.run",
    "audit.read",
    "memory.read",
]

KANALOA_READONLY_SCOPES: list[str] = [
    "system.read_capabilities",
    "agents.list",
    "agents.read",
    "adapters.list",
    "adapters.status",
    "tools.list",
    "mcp.list",
    "tasks.read",
    "audit.read",
    "memory.read",
]

# Back-compat alias for imports expecting “default” = owner.
KANALOA_DEFAULT_SCOPES = KANALOA_OWNER_SCOPES


def _profile_mark(phases: list[dict[str, Any]], name: str, phase_started: float) -> float:
    now = perf_counter()
    phases.append({"name": name, "ms": round((now - phase_started) * 1000, 2)})
    return now


def scopes_for_permission_profile(profile: str) -> list[str]:
    if profile == "safe":
        return list(KANALOA_SAFE_SCOPES)
    if profile == "readonly":
        return list(KANALOA_READONLY_SCOPES)
    return list(KANALOA_OWNER_SCOPES)

HIGH_RISK_SCOPES: frozenset[str] = frozenset(
    {
        "secrets.read",
        "env.read_raw",
        "shell.exec",
        "workspace.read_unrestricted",
    }
)


def get_claude_code_command() -> str:
    return (os.getenv("CLAUDE_CODE_COMMAND") or "claude").strip() or "claude"


def get_codex_command() -> str:
    return (os.getenv("CODEX_COMMAND") or "codex").strip() or "codex"


def get_environment_name() -> str:
    raw = (os.getenv("OCTOPUS_ENV") or os.getenv("ENV") or "development").strip().lower()
    if raw in ("prod", "production"):
        return "production"
    if raw in ("dev", "development", "local"):
        return "development"
    return raw or "development"


def is_adapter_execute_enabled() -> bool:
    raw = (os.getenv("OCTOPUS_KANALOA_ADAPTER_EXECUTE") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_skill_tools() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sk in skills_repo.list()[:64]:
        items.append(
            {
                "id": f"skill:{sk.skill_id}",
                "name": sk.name or sk.skill_id,
                "kind": "skill",
                "skill_id": sk.skill_id,
                "enabled": bool(sk.enabled),
            }
        )
    return items


def _internal_tools_catalog() -> list[dict[str, Any]]:
    """Logical tools Kanaloa uses server-side (HTTP surfaces); no secrets."""
    return [
        {"id": "read_platform_capabilities", "kind": "internal", "endpoint": "GET /api/system/capabilities"},
        {"id": "list_agents", "kind": "internal", "endpoint": "GET /agents"},
        {"id": "list_adapters_status", "kind": "internal", "endpoint": "GET /api/adapters/status"},
        {"id": "dispatch_claude_adapter", "kind": "internal", "endpoint": "POST /api/adapters/claude-code/dispatch"},
        {"id": "create_task", "kind": "internal", "endpoint": "POST /tasks"},
        {"id": "read_audit_watchdog", "kind": "internal", "endpoint": "GET /watchdog"},
        {"id": "kanaloa_create_task", "kind": "internal", "endpoint": "POST /api/kanaloa/actions/create-task"},
        {"id": "kanaloa_dispatch", "kind": "internal", "endpoint": "POST /api/kanaloa/actions/dispatch"},
        {"id": "kanaloa_task_status", "kind": "internal", "endpoint": "GET /api/kanaloa/actions/task/{task_id}"},
        {"id": "kanaloa_task_events", "kind": "internal", "endpoint": "GET /api/kanaloa/actions/task/{task_id}/events"},
        {"id": "kanaloa_cancel", "kind": "internal", "endpoint": "POST /api/kanaloa/actions/cancel"},
        {"id": "kanaloa_recent_tasks", "kind": "internal", "endpoint": "GET /api/kanaloa/actions/recent-tasks"},
        {"id": "kanaloa_orchestrator_run", "kind": "internal", "endpoint": "POST /api/kanaloa/orchestrator/run"},
        {"id": "kanaloa_orchestrator_tasks", "kind": "internal", "endpoint": "GET /api/kanaloa/orchestrator/tasks"},
    ]


def _adapter_registry_static() -> list[dict[str, Any]]:
    return [
        {
            "id": "claude_code",
            "name": "Claude Code",
            "type": "external_cli_or_handoff",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "owner_execute_default",
            "required_env": ["OCTOPUS_LOCAL_BRIDGE_URL", "Optional: CLAUDE_CODE_COMMAND"],
            "capabilities": ["cli_execute_if_installed", "handoff_file", "bridge_callback"],
        },
        {
            "id": "codex_cli",
            "name": "Codex",
            "type": "external_cli_or_handoff",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "owner_execute_default",
            "required_env": ["OCTOPUS_LOCAL_BRIDGE_URL", "Optional: CODEX_COMMAND"],
            "capabilities": ["cli_execute_if_installed", "handoff_file", "bridge_callback"],
        },
        {
            "id": "cursor_cli",
            "name": "Cursor",
            "type": "ide_handoff",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "handoff_only",
            "required_env": ["OCTOPUS_LOCAL_BRIDGE_URL"],
            "capabilities": ["handoff_markdown", "version_probe_optional"],
        },
        {
            "id": "openclaw_http",
            "name": "OpenClaw HTTP",
            "type": "webhook_or_handoff",
            "enabled": True,
            "configured": bool(get_openclaw_webhook_url()),
            "audit_enabled": True,
            "safe_dispatch_mode": "webhook_or_handoff",
            "required_env": ["OPENCLAW_WEBHOOK_URL (on Bridge host)"],
            "capabilities": ["http_post_when_configured"],
        },
        {
            "id": "http_agent",
            "name": "HTTP / Webhook Agent (generic)",
            "type": "webhook_or_handoff",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "webhook_or_handoff",
            "required_env": ["per-agent control_plane.webhook_url"],
            "capabilities": ["http_post_per_agent", "handoff_fallback", "bridge_callback"],
            "details": "Connect any agent that accepts an HTTP webhook; URL is configured per agent.",
        },
        {
            "id": "cli_agent",
            "name": "CLI Agent (generic)",
            "type": "external_cli_or_handoff",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "owner_execute_default",
            "required_env": ["per-agent control_plane.cli_path"],
            "capabilities": ["cli_execute_per_agent", "handoff_fallback", "bridge_callback"],
            "details": "Connect any command-line agent; the command is configured per agent.",
        },
        {
            "id": "local_bridge",
            "name": "Local Bridge",
            "type": "execution_gateway",
            "enabled": True,
            "configured": True,
            "audit_enabled": True,
            "safe_dispatch_mode": "bridge_rpc",
            "required_env": ["OCTOPUS_LOCAL_BRIDGE_URL", "Optional: OCTOPUS_BRIDGE_SHARED_SECRET"],
            "capabilities": ["route_external_adapters"],
        },
        {
            "id": "mcp_server",
            "name": "MCP",
            "type": "future_or_external",
            "enabled": False,
            "configured": False,
            "audit_enabled": False,
            "safe_dispatch_mode": "none",
            "required_env": [],
            "capabilities": [],
            "details": "No first-party MCP registry in API yet; reserved.",
        },
    ]


def build_claude_code_status(probe: dict[str, Any]) -> dict[str, Any]:
    bridge_ok = probe.get("reachable") is True
    bs = probe.get("bridge_status") or {}
    cmd = get_claude_code_command()
    bin0 = cmd.split()[0] if cmd else "claude"
    api_host_has_cli = bool(shutil.which(bin0))
    bridge_reports_cli = bool(bs.get("claude_on_path"))

    agents = agents_repo.list()
    has_claude_agent = any((a.adapter_id or "") == "claude_code" for a in agents)
    configured = has_claude_agent or bool(os.getenv("CLAUDE_CODE_COMMAND"))

    if not bridge_ok:
        return {
            "configured": configured,
            "enabled": False,
            "available": False,
            "health": "error",
            "command": bin0,
            "details": "Local Bridge unreachable from API; start apps/local-bridge and verify OCTOPUS_LOCAL_BRIDGE_URL.",
        }

    if not configured:
        return {
            "configured": False,
            "enabled": False,
            "available": False,
            "health": "missing_config",
            "command": bin0,
            "details": (
                "No Claude Code agent (adapter claude_code) registered and CLAUDE_CODE_COMMAND unset. "
                "Add one via /agents/add or set CLAUDE_CODE_COMMAND."
            ),
        }

    cli_ok = bridge_reports_cli or api_host_has_cli
    if not cli_ok:
        return {
            "configured": True,
            "enabled": False,
            "available": False,
            "health": "not_installed",
            "command": bin0,
            "details": (
                "`claude` executable not found on Bridge PATH (and not on API host). "
                "Install Claude Code CLI or set CLAUDE_CODE_COMMAND."
            ),
        }

    if has_claude_agent:
        enabled_flag = any((a.adapter_id or "") == "claude_code" and a.enabled for a in agents)
    else:
        enabled_flag = True  # CLI present + Bridge up; no registry row yet (env-only).
    return {
        "configured": True,
        "enabled": enabled_flag,
        "available": True,
        "health": "ok",
        "command": bin0,
        "details": (
            "Bridge reports Claude CLI on PATH."
            if bridge_reports_cli
            else "API host sees Claude CLI on PATH (Bridge status did not include claude_on_path)."
        ),
    }


def build_codex_status(probe: dict[str, Any]) -> dict[str, Any]:
    bridge_ok = probe.get("reachable") is True
    bs = probe.get("bridge_status") or {}
    cmd = get_codex_command()
    bin0 = cmd.split()[0] if cmd else "codex"
    api_host_has_cli = bool(shutil.which(bin0))
    bridge_reports_cli = bool(bs.get("codex_on_path"))

    agents = agents_repo.list()
    has_codex_agent = any((a.adapter_id or "") == "codex_cli" for a in agents)
    configured = has_codex_agent or bool(os.getenv("CODEX_COMMAND"))

    if not bridge_ok:
        return {
            "configured": configured,
            "enabled": False,
            "available": False,
            "health": "error",
            "command": bin0,
            "details": "Local Bridge unreachable from API; start apps/local-bridge and verify OCTOPUS_LOCAL_BRIDGE_URL.",
        }

    if not configured:
        return {
            "configured": False,
            "enabled": False,
            "available": False,
            "health": "missing_config",
            "command": bin0,
            "details": (
                "No Codex agent (adapter codex_cli) registered and CODEX_COMMAND unset. "
                "Add one via /agents/add or set CODEX_COMMAND."
            ),
        }

    cli_ok = bridge_reports_cli or api_host_has_cli
    if not cli_ok:
        return {
            "configured": True,
            "enabled": False,
            "available": False,
            "health": "not_installed",
            "command": bin0,
            "details": (
                "`codex` executable not found on Bridge PATH (and not on API host). "
                "Install the Codex CLI or set CODEX_COMMAND; tasks fall back to handoff files."
            ),
        }

    enabled_flag = (
        any((a.adapter_id or "") == "codex_cli" and a.enabled for a in agents)
        if has_codex_agent
        else True
    )
    return {
        "configured": True,
        "enabled": enabled_flag,
        "available": True,
        "health": "ok",
        "command": bin0,
        "details": (
            "Bridge reports Codex CLI on PATH (`codex exec`)."
            if bridge_reports_cli
            else "API host sees Codex CLI on PATH (Bridge status did not include codex_on_path)."
        ),
    }


def build_cursor_status(probe: dict[str, Any]) -> dict[str, Any]:
    bridge_ok = probe.get("reachable") is True
    bs = probe.get("bridge_status") or {}
    cursor_on_path = bool(bs.get("cursor_on_path"))

    # No dedicated Cursor MCP server in-repo; integration is Bridge handoff / optional CLI probe.
    if not bridge_ok:
        return {
            "configured": False,
            "enabled": False,
            "available": False,
            "health": "error",
            "details": "Local Bridge unreachable; Cursor handoff path cannot run.",
        }

    if not cursor_on_path:
        return {
            "configured": False,
            "enabled": False,
            "available": False,
            "health": "unsupported",
            "details": (
                "Cursor has no stable headless automation contract in this platform. "
                "Bridge can write handoff markdown when you register a cursor_cli agent; "
                "`cursor` CLI was not detected on the Bridge host PATH. "
                "No active Cursor MCP bridge is registered in this deployment."
            ),
        }

    return {
        "configured": True,
        "enabled": True,
        "available": False,
        "health": "not_configured",
        "details": (
            "`cursor` CLI detected on Bridge host, but Cursor remains an IDE-first product: "
            "automation is handoff-assisted + manual IDE steps + optional callback — "
            "not a guaranteed remote headless session."
        ),
    }


def build_adapters_status_payload(*, bridge_probe: dict[str, Any] | None = None) -> dict[str, Any]:
    started = perf_counter()
    phases: list[dict[str, Any]] = []
    phase_started = perf_counter()
    probe = bridge_probe if bridge_probe is not None else probe_local_bridge_detailed()
    phase_started = _profile_mark(phases, "probe_local_bridge", phase_started)
    cc = build_claude_code_status(probe)
    phase_started = _profile_mark(phases, "claude_code_status", phase_started)
    cx = build_codex_status(probe)
    phase_started = _profile_mark(phases, "codex_status", phase_started)
    cu = build_cursor_status(probe)
    phase_started = _profile_mark(phases, "cursor_status", phase_started)
    openclaw_url = get_openclaw_webhook_url()
    ob = probe.get("bridge_status") or {}
    openclaw_configured = bool(openclaw_url) or bool(ob.get("openclaw_configured"))
    phase_started = _profile_mark(phases, "openclaw_status", phase_started)

    return {
        "local_bridge": {
            "url": probe.get("url"),
            "reachable": probe.get("reachable"),
            "probed_at": probe.get("probed_at"),
            "health": "ok" if probe.get("reachable") else "error",
            "details": (probe.get("hints") or [""])[0],
        },
        "claude_code": {k: v for k, v in cc.items()},
        "codex_cli": {k: v for k, v in cx.items()},
        "cursor": {k: v for k, v in cu.items()},
        "openclaw_http": {
            "configured": openclaw_configured,
            "enabled": bool(openclaw_url),
            "available": openclaw_configured,
            "health": "ok" if openclaw_configured else "missing_config",
            "details": (
                "OPENCLAW_WEBHOOK_URL set on Bridge host"
                if openclaw_url
                else "OPENCLAW_WEBHOOK_URL not set; OpenClaw adapter falls back to handoff files."
            ),
        },
        "_schema": "adapters_status_v1",
        "_profile": {"total_ms": round((perf_counter() - started) * 1000, 2), "phases": phases},
    }


def _agent_status_for(a) -> str:
    if not getattr(a, "enabled", True):
        return "disabled"
    if a.type == "external" and (a.adapter_id or "") in {"claude_code", "codex_cli", "cursor_cli", "openclaw_http"}:
        return "available"
    if a.agent_id == KANALOA_AGENT_ID:
        return "available"
    return "available"


def build_agent_registry_entries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in agents_repo.list():
        perms = []
        if a.adapter_id in ("claude_code", "codex_cli"):
            perms = ["adapters.dispatch", "bridge.execute_conditional"]
        elif a.adapter_id == "cursor_cli":
            perms = ["adapters.dispatch", "handoff.callback"]
        out.append(
            {
                "id": a.agent_id,
                "name": a.display_name,
                "type": "builtin" if a.type == "builtin" else "external_execution_agent",
                "adapter": a.adapter_id,
                "enabled": bool(a.enabled),
                "permissions_required": perms,
                "status": _agent_status_for(a),
            }
        )
    return out


def build_capabilities_payload() -> dict[str, Any]:
    started = perf_counter()
    phases: list[dict[str, Any]] = []
    phase_started = perf_counter()
    probe = probe_local_bridge_detailed()
    phase_started = _profile_mark(phases, "probe_local_bridge", phase_started)
    adapters_status = build_adapters_status_payload(bridge_probe=probe)
    phase_started = _profile_mark(phases, "build_adapters_status", phase_started)
    api_version = "2.0.0"
    perm_profile = get_kane_permission_profile()
    eff_scopes = scopes_for_permission_profile(perm_profile)
    phase_started = _profile_mark(phases, "permissions", phase_started)

    agents_min = []
    for row in build_agent_registry_entries():
        agents_min.append(
            {
                "id": row["id"],
                "name": row["name"],
                "type": "internal_orchestrator" if row["id"] == KANALOA_AGENT_ID else row["type"],
                "enabled": row["enabled"],
            }
        )
    phase_started = _profile_mark(phases, "agent_registry", phase_started)
    safe_tools = _safe_skill_tools()
    phase_started = _profile_mark(phases, "safe_skill_tools", phase_started)
    internal_tools = _internal_tools_catalog()
    phase_started = _profile_mark(phases, "internal_tools", phase_started)

    return {
        "platform": {
            "name": APP_NAME,
            "version": api_version,
            "environment": get_environment_name(),
            "persistence": get_persistence_backend(),
        },
        "kanaloa": {
            "agent_id": KANALOA_AGENT_ID,
            "role": "orchestrator_agent",
            "permission_profile": perm_profile,
            "permissions": eff_scopes,
            "tools": internal_tools,
            "llm_configured": is_llm_configured(),
        },
        "agents": agents_min,
        "tools": safe_tools + internal_tools,
        "adapters": _adapter_registry_static(),
        "mcpServers": [],
        "tasks": {"enabled": True},
        "audit": {"enabled": True, "note": "Watchdog + task events; use GET /watchdog and task timelines."},
        "adapters_live": {
            "claude_code": adapters_status["claude_code"],
            "codex_cli": adapters_status["codex_cli"],
            "cursor": adapters_status["cursor"],
            "local_bridge": adapters_status["local_bridge"],
            "openclaw_http": adapters_status["openclaw_http"],
        },
        "bridge_probe": {
            "reachable": probe.get("reachable"),
            "probed_at": probe.get("probed_at"),
        },
        "_schema": "capabilities_v1",
        "_profile": {"total_ms": round((perf_counter() - started) * 1000, 2), "phases": phases},
    }


def build_compact_snapshot_text() -> str:
    """Inject into Kanaloa LLM context — facts only, no secrets."""
    cap = build_capabilities_payload()
    slim = {
        "environment": cap["platform"]["environment"],
        "permission_profile": cap["kanaloa"].get("permission_profile"),
        "kanaloa_permissions": cap["kanaloa"]["permissions"],
        "llm_configured": cap["kanaloa"]["llm_configured"],
        "agents_count": len(cap["agents"]),
        "adapters_live": cap["adapters_live"],
        "internal_tools": [t["id"] for t in cap["kanaloa"]["tools"]],
        "mcpServers": "none_registered_in_api",
    }
    return json.dumps(slim, ensure_ascii=False, indent=2)


def should_inject_platform_truth(user_text: str) -> bool:
    if not user_text:
        return False
    q = user_text.lower()
    keys = (
        "cursor",
        "claude",
        "claude code",
        "连接",
        "bridge",
        "adapter",
        "适配",
        "工具",
        "权限",
        "mcp",
        "agent",
        "kanaloa",
        "平台",
        "capabilities",
        "调度",
        "任务状态",
        "真实",
        "是否",
        "章鱼",
        "kāne",
        "kane",
    )
    return any(k in q for k in keys)

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import (
    Agent,
    AgentCapabilities,
    AgentControlPlaneConfig,
    AgentCreateBody,
    AgentPatchBody,
    AgentStatus,
    TaskAssignBody,
    TaskCreateBody,
)
from ..store.repositories import agents_repo, tasks_repo
from .task_lifecycle import assign_task, create_task, run_task


def _default_capabilities(adapter_id: str) -> AgentCapabilities:
    if adapter_id == "openclaw_http":
        return AgentCapabilities(
            can_chat=True,
            can_code=False,
            can_browse=True,
            can_use_skills=False,
            can_stream=True,
            supports_structured_task=True,
            supports_handoff=True,
            supports_callback=True,
        )
    if adapter_id == "cursor_cli":
        return AgentCapabilities(
            can_chat=False,
            can_code=True,
            can_browse=False,
            can_use_skills=False,
            can_run_local_commands=True,
            supports_structured_task=True,
            supports_handoff=True,
            supports_callback=True,
        )
    if adapter_id == "claude_code":
        return AgentCapabilities(
            can_chat=False,
            can_code=True,
            can_browse=False,
            can_use_skills=False,
            can_run_local_commands=True,
            supports_structured_task=True,
            supports_handoff=True,
            supports_callback=True,
        )
    if adapter_id == "local_script":
        return AgentCapabilities(
            can_chat=False,
            can_code=False,
            can_browse=False,
            can_use_skills=False,
            can_run_local_commands=True,
            supports_structured_task=True,
            supports_handoff=False,
            supports_callback=False,
        )
    return AgentCapabilities()


def create_control_plane_agent(body: AgentCreateBody) -> Agent:
    aid = (body.agent_id or "").strip() or new_id("agent")
    if agents_repo.get(aid):
        raise HTTPException(status_code=409, detail="agent_id_conflict")
    caps = body.capabilities or _default_capabilities(body.adapter_id)
    agent = Agent(
        agent_id=aid,
        display_name=body.display_name,
        type=body.type,
        status=AgentStatus.idle,
        capabilities=caps,
        adapter_id=body.adapter_id,
        integration_mode=body.integration_mode,
        integration_channels=list(body.integration_channels),
        control_depth=body.control_depth,
        control_plane=body.control_plane,
    )
    agents_repo.upsert(agent)
    return agent


def patch_control_plane_agent(agent_id: str, body: AgentPatchBody) -> Agent:
    cur = agents_repo.get(agent_id)
    if not cur:
        raise HTTPException(status_code=404, detail="agent_not_found")
    data = cur.model_dump()
    if body.display_name is not None:
        data["display_name"] = body.display_name
    if body.adapter_id is not None:
        data["adapter_id"] = body.adapter_id
    if body.integration_mode is not None:
        data["integration_mode"] = body.integration_mode
    if body.integration_channels is not None:
        data["integration_channels"] = list(body.integration_channels)
    if body.control_depth is not None:
        data["control_depth"] = body.control_depth
    if body.capabilities is not None:
        data["capabilities"] = body.capabilities.model_dump(mode="json")
    if body.control_plane is not None:
        merged = (cur.control_plane.model_dump() if cur.control_plane else {}) | body.control_plane.model_dump(
            exclude_none=True
        )
        data["control_plane"] = AgentControlPlaneConfig.model_validate(merged)
    if body.enabled is not None:
        data["enabled"] = bool(body.enabled)
    out = Agent.model_validate(data)
    agents_repo.upsert(out)
    return out


def delete_control_plane_agent(agent_id: str) -> dict[str, Any]:
    agent = agents_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    # 守门：内置 Kanaloa（octopus_builtin）不允许删除，只能禁用
    if agent.type == "builtin" or (agent.adapter_id or "") == "builtin_octopus":
        raise HTTPException(
            status_code=400,
            detail="builtin_agent_cannot_be_deleted; use PATCH with enabled=false instead",
        )
    try:
        agents_repo.delete(agent_id)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"delete_failed: {exc}") from exc
    return {"agent_id": agent_id, "deleted": True}


def _test_description(adapter_id: str) -> str:
    if adapter_id == "openclaw_http":
        return "OpenClaw connectivity test: deliver this short task via Bridge/webhook path and return an acknowledgement."
    if adapter_id == "cursor_cli":
        return "Cursor external test: follow the handoff instructions (assisted control; not headless automation)."
    if adapter_id == "claude_code":
        return "Claude Code test: echo a one-line confirmation of CLI or handoff path (do not request destructive actions)."
    if adapter_id == "local_script":
        return "Local script test run (shell_command from agent control_plane is preferred)."
    return "Generic agent connectivity test from Octopus control plane."


def start_agent_test_run(agent_id: str) -> dict[str, Any]:
    agent = agents_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    if agent.type == "builtin" or (agent.adapter_id or "") == "builtin_octopus":
        title = f"[Control plane test] builtin {agent_id}"
        desc = "Builtin test: confirm in-process executor returns structured output."
    else:
        title = f"[Control plane test] {agent_id}"
        desc = _test_description(agent.adapter_id or "")

    task = create_task(
        TaskCreateBody(title=title, description=desc, execution_mode="commander"),
    )
    assign_task(task.task_id, TaskAssignBody(agent_id=agent_id))
    run_out = run_task(task.task_id)
    run = run_out.get("run")
    run_id = getattr(run, "run_id", None) if run is not None else None
    task2 = tasks_repo.get(task.task_id)
    return {
        "ok": True,
        "agent_id": agent_id,
        "task_id": task.task_id,
        "run_id": run_id,
        "queued": bool(run_out.get("queued")),
        "pending_approval": bool(run_out.get("pending_approval")),
        "task_status": task2.status.value if task2 else None,
        "hints": [
            "Poll GET /tasks/{task_id} until status is terminal (succeeded / failed / waiting_approval).",
            "For handoff adapters, complete via POST /integrations/bridge/complete with task_id and run_id.",
        ],
    }


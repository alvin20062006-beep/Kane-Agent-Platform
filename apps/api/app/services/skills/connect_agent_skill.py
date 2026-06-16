"""Platform skill: stepwise external agent connection (probe → draft → register → test)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ...models import (
    AgentCapabilities,
    AgentCreateBody,
    LocalBridgeRegisterBody,
    SkillExecuteBody,
    SkillExecuteResult,
)
from ...settings_env import get_api_public_url
from ..control_plane_agents import create_control_plane_agent, start_agent_test_run
from ..kanaloa_platform import probe_local_bridge_detailed
from ..task_lifecycle import register_local_bridge_agent

CONNECT_MODES = frozenset({"http_webhook", "cli_sync", "handoff_only", "local_script"})
CONNECT_STEPS = frozenset({"guide", "probe", "draft", "register", "test_run", "handoff_guide"})

_GUIDE_STEPS: list[dict[str, str]] = [
    {"id": "probe", "title": "检查 API 与 Local Bridge", "detail": "确认控制面与本机 Bridge 在线。"},
    {"id": "choose_mode", "title": "选择连接方式", "detail": "推荐 HTTP/Webhook 通用 Agent；CLI 同步或 handoff 按需选择。"},
    {"id": "draft", "title": "生成 Agent 配置草稿", "detail": "填写 webhook_url、cli_path 或 shell_command，预览 adapter 与 completion_mode。"},
    {"id": "register", "title": "登记到平台与 Bridge", "detail": "确认后创建 Agent 并 POST /local-bridge/register。"},
    {"id": "test_run", "title": "试跑连通性", "detail": "触发 test-run，handoff 场景按 callback 说明完成。"},
]


def _caps_for_adapter(adapter_id: str) -> AgentCapabilities:
    if adapter_id == "local_script":
        return AgentCapabilities(
            can_run_local_commands=True,
            supports_structured_task=True,
        )
    return AgentCapabilities(
        can_code=True,
        supports_structured_task=True,
        supports_handoff=True,
        supports_callback=True,
        can_run_local_commands=adapter_id == "cli_agent",
    )


def _draft_from_mode(mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    display_name = str(payload.get("display_name") or "My External Agent").strip()[:500]
    agent_id = str(payload.get("agent_id") or "").strip() or None

    if mode == "http_webhook":
        webhook_url = str(payload.get("webhook_url") or "").strip()
        adapter_id = "http_agent"
        control_plane: dict[str, Any] = {"webhook_url": webhook_url, "callback_public_base_url": get_api_public_url()}
        channels = ["bridge", "webhook", "handoff", "callback"]
        completion_mode = "handoff_callback" if not webhook_url else "bridge_sync"
        integration_mode = "external"
        control_depth = "partial"
    elif mode == "cli_sync":
        cli_path = str(payload.get("cli_path") or "").strip()
        adapter_id = "cli_agent"
        control_plane = {"cli_path": cli_path, "callback_public_base_url": get_api_public_url()}
        channels = ["bridge", "cli", "handoff", "callback"]
        completion_mode = "handoff_callback" if not cli_path else "bridge_sync"
        integration_mode = "external"
        control_depth = "partial"
    elif mode == "handoff_only":
        adapter_id = "http_agent"
        control_plane = {"callback_public_base_url": get_api_public_url()}
        channels = ["bridge", "handoff", "callback"]
        completion_mode = "handoff_callback"
        integration_mode = "external"
        control_depth = "assisted"
    elif mode == "local_script":
        shell_command = str(payload.get("shell_command") or "echo kane-bridge-ok").strip()
        adapter_id = "local_script"
        control_plane = {"shell_command": shell_command, "allow_local_script": True}
        channels = ["bridge", "shell"]
        completion_mode = "bridge_sync"
        integration_mode = "embedded"
        control_depth = "partial"
    else:
        raise HTTPException(status_code=400, detail="invalid_connect_mode")

    return {
        "agent_create_body": {
            "agent_id": agent_id,
            "display_name": display_name,
            "type": "external",
            "adapter_id": adapter_id,
            "integration_mode": integration_mode,
            "integration_channels": channels,
            "control_depth": control_depth,
            "capabilities": _caps_for_adapter(adapter_id).model_dump(mode="json"),
            "control_plane": control_plane,
        },
        "completion_mode": completion_mode,
        "mode": mode,
    }


def execute_connect_agent_skill(input_payload: dict[str, Any], body: SkillExecuteBody) -> SkillExecuteResult:
    step = str(input_payload.get("step") or "guide").strip().lower()
    if step not in CONNECT_STEPS:
        return SkillExecuteResult(ok=False, error="invalid_connect_step", meta={"allowed_steps": sorted(CONNECT_STEPS)})

    if step == "guide":
        return SkillExecuteResult(
            ok=True,
            output={
                "skill_id": "skill_connect_agent",
                "title": "连接外部 Agent（说明书）",
                "steps": _GUIDE_STEPS,
                "recommended_mode": "http_webhook",
                "api_public_url": get_api_public_url(),
            },
            meta={"kind": "connect_agent", "step": "guide"},
        )

    if step == "probe":
        probe = probe_local_bridge_detailed()
        bridge_ok = probe.get("reachable") is True
        hints = probe.get("hints") or []
        if bridge_ok:
            natural_language = "API 与 Local Bridge 已就绪，可以选择连接方式并生成 Agent 草稿。"
        else:
            natural_language = (
                "Local Bridge 暂不可达。请先运行 npm run dev:bridge（或 dev:stack），"
                "确认 OCTOPUS_LOCAL_BRIDGE_URL 与 Bridge 进程一致后再继续。"
            )
        if hints:
            natural_language += " " + " ".join(str(h) for h in hints[:2])
        return SkillExecuteResult(
            ok=bridge_ok,
            output={
                "api_assumed_ok": True,
                "bridge": probe,
                "ready": bridge_ok,
                "next_step": "draft" if bridge_ok else "fix_bridge",
                "hints": hints,
                "natural_language": natural_language,
            },
            error=None if bridge_ok else "bridge_unreachable",
            meta={"kind": "connect_agent", "step": "probe"},
        )

    if step == "draft":
        mode = str(input_payload.get("mode") or "http_webhook").strip().lower()
        if mode not in CONNECT_MODES:
            return SkillExecuteResult(ok=False, error="invalid_connect_mode", meta={"allowed_modes": sorted(CONNECT_MODES)})
        draft = _draft_from_mode(mode, input_payload)
        return SkillExecuteResult(
            ok=True,
            output=draft,
            meta={"kind": "connect_agent", "step": "draft"},
        )

    if step == "register":
        if not input_payload.get("confirmed"):
            return SkillExecuteResult(
                ok=False,
                error="confirmation_required",
                meta={"kind": "connect_agent", "step": "register"},
            )
        mode = str(input_payload.get("mode") or "http_webhook").strip().lower()
        draft = _draft_from_mode(mode, input_payload)
        create_body = AgentCreateBody.model_validate(draft["agent_create_body"])
        agent = create_control_plane_agent(create_body)
        bridge_state = None
        if input_payload.get("register_bridge", True):
            caps = {k: v for k, v in agent.capabilities.model_dump(mode="json").items() if isinstance(v, bool)}
            bridge_state = register_local_bridge_agent(
                LocalBridgeRegisterBody(
                    agent_id=agent.agent_id,
                    display_name=agent.display_name,
                    adapter_id=agent.adapter_id or "http_agent",
                    capabilities=caps,
                    status="online",
                )
            )
        return SkillExecuteResult(
            ok=True,
            output={
                "agent_id": agent.agent_id,
                "display_name": agent.display_name,
                "adapter_id": agent.adapter_id,
                "completion_mode": draft["completion_mode"],
                "bridge_registered": bridge_state is not None,
                "fleet_url": f"/agent-fleet/{agent.agent_id}",
                "bridge_url": "/local-bridge",
                "next_step": "test_run",
            },
            meta={"kind": "connect_agent", "step": "register"},
        )

    if step == "test_run":
        agent_id = str(input_payload.get("agent_id") or "").strip()
        if not agent_id:
            return SkillExecuteResult(ok=False, error="agent_id_required", meta={"step": "test_run"})
        result = start_agent_test_run(agent_id)
        return SkillExecuteResult(
            ok=True,
            output=result,
            meta={"kind": "connect_agent", "step": "test_run"},
        )

    if step == "handoff_guide":
        callback = f"{get_api_public_url()}/integrations/bridge/complete"
        return SkillExecuteResult(
            ok=True,
            output={
                "skill_id": "skill_connect_agent",
                "title": "Handoff + Callback 说明书",
                "completion_mode": "handoff_callback",
                "callback_url": callback,
                "handoff_file_pattern": "{task_id}_{run_id}.md",
                "steps": [
                    {
                        "id": "dispatch",
                        "title": "下发任务",
                        "detail": "分配外部 Agent 并运行；Bridge 在 handoff 目录写入 markdown（含 frontmatter）。",
                    },
                    {
                        "id": "external_work",
                        "title": "在外部工具完成",
                        "detail": "打开 handoff 文件中的 Prompt，在 IDE / CLI / 网页 Agent 中执行。",
                    },
                    {
                        "id": "callback",
                        "title": "POST callback",
                        "detail": f"完成后 POST {callback}，携带 task_id、run_id、status、output。",
                    },
                ],
                "bridge_url": "/local-bridge",
                "docs": "docs/EXTERNAL_AGENT_INTEGRATION.md",
            },
            meta={"kind": "connect_agent", "step": "handoff_guide"},
        )

    return SkillExecuteResult(ok=False, error="unhandled_connect_step")

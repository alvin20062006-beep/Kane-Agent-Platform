from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .models import Agent, Run, Task
from .services.api_profiles import resolve_profile_for_agent
from .services.llm_client import LLMNotConfiguredError, call_llm
from .settings_env import (
    get_bridge_default_retry_limit,
    get_bridge_default_timeout_seconds,
    get_bridge_shared_secret,
    get_local_bridge_url,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class ExecuteResult:
    integration_path: str
    ok: bool
    output: str | None
    error: str | None
    meta: dict[str, Any] | None = None
    pending_handoff: bool = False


def execute_builtin_octopus(task: Task, run: Run, agent: Agent) -> ExecuteResult:
    """
    Builtin Octopus executor.
    If an API Profile is bound to octopus_builtin, calls the real LLM for planning
    and execution. Falls back to deterministic mode when no profile is configured.
    """
    text = f"{task.title}\n{task.description or ''}".lower()
    if any(flag in text for flag in ("simulate_fail", "fail this", "[fail]", "force_error")):
        return ExecuteResult(
            integration_path="builtin_sync",
            ok=False,
            output=None,
            error="simulated_builtin_failure",
            meta={
                "reason": "The task content requested an honest simulated failure path.",
                "hint": "Retry after updating the task intent or assign to a different agent.",
            },
        )

    # Try LLM-powered execution
    system_prompt = (
        "你是章鱼 AI（Octopus AI），负责执行用户交给你的任务。"
        "请分析任务内容，给出清晰的执行计划和结果摘要。"
        "如果任务需要外部工具或 API，请说明所需步骤。"
        "用中文回答，简洁、专业。"
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"任务标题：{task.title}\n"
                f"任务描述：{task.description or '（无描述）'}\n"
                f"执行模式：{task.execution_mode}\n"
                "请给出执行计划和初步结果。"
            ),
        },
    ]

    try:
        llm_output = call_llm(messages)
        out = {
            "agent": agent.agent_id,
            "title": task.title,
            "execution_mode": task.execution_mode,
            "run_id": run.run_id,
            "llm_powered": True,
            "result": llm_output,
        }
        return ExecuteResult(
            integration_path="builtin_llm",
            ok=True,
            output=json.dumps(out, ensure_ascii=False, indent=2),
            error=None,
            meta={"llm_powered": True},
        )
    except LLMNotConfiguredError:
        # Deterministic fallback
        steps = ["parse_task", "plan_minimal_steps", "simulate_tool_calls", "summarize"]
        out = {
            "agent": agent.agent_id,
            "title": task.title,
            "description": task.description,
            "execution_mode": task.execution_mode,
            "run_id": run.run_id,
            "plan": steps,
            "llm_powered": False,
            "result": (
                "章鱼 AI 以确定性模式完成任务（未配置 LLM 模型）。"
                "前往「设置 → 模型」绑定 API Profile 后可启用真实 AI 推理。"
            ),
        }
        return ExecuteResult(
            integration_path="builtin_sync",
            ok=True,
            output=json.dumps(out, ensure_ascii=False, indent=2),
            error=None,
            meta={"steps": steps, "llm_powered": False},
        )
    except RuntimeError as e:
        return ExecuteResult(
            integration_path="builtin_llm_error",
            ok=False,
            output=None,
            error=str(e),
            meta={"hint": "Check API profile configuration and model endpoint."},
        )


def execute_via_local_bridge(task: Task, run: Run, agent: Agent) -> ExecuteResult:
    """
    Forward execution to Local Bridge (real HTTP). Bridge may run Claude CLI, write handoff, or HTTP to OpenClaw.
    If bridge is down: return honest error (not fake success).
    """
    control_plane = agent.control_plane
    bridge_route = control_plane.bridge_route if control_plane and control_plane.bridge_route else "/v1/execute"
    url = f"{get_local_bridge_url()}{bridge_route}"
    profile = resolve_profile_for_agent(agent.agent_id)
    cp_payload = None
    if control_plane:
        cp_payload = control_plane.model_dump(exclude_none=True)
    timeout_seconds = (
        control_plane.bridge_timeout_seconds
        if control_plane and control_plane.bridge_timeout_seconds is not None
        else get_bridge_default_timeout_seconds()
    )
    retry_limit = (
        control_plane.bridge_retry_limit
        if control_plane and control_plane.bridge_retry_limit is not None
        else get_bridge_default_retry_limit()
    )
    payload = {
        "task_id": task.task_id,
        "run_id": run.run_id,
        "agent_id": agent.agent_id,
        "adapter_id": agent.adapter_id or "unknown",
        "title": task.title,
        "description": task.description,
        "execution_mode": task.execution_mode,
        "agent_control_plane": cp_payload,
        "api_profile": (
            {
                "profile_id": profile.profile_id,
                "provider": profile.provider.value,
                "base_url": profile.base_url,
                "model": profile.model,
                # Runtime key for Bridge CLI only — never written to handoff files (Bridge redacts).
                "api_key": profile.api_key,
            }
            if profile
            else None
        ),
    }
    headers: dict[str, str] = {}
    secret = get_bridge_shared_secret()
    if secret:
        headers["X-Octopus-Bridge-Key"] = secret

    last_error: str | None = None
    for attempt in range(retry_limit + 1):
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                r = client.post(url, json=payload, headers=headers)
                if r.status_code >= 500 and attempt < retry_limit:
                    last_error = f"bridge_http_{r.status_code}"
                    continue
                if r.status_code >= 400:
                    return ExecuteResult(
                        integration_path="local_bridge_http",
                        ok=False,
                        output=r.text[:8000] if r.text else None,
                        error=f"bridge_http_{r.status_code}",
                        meta={"url": url, "timeout_seconds": timeout_seconds, "retry_limit": retry_limit},
                    )
                data = r.json()
                ok = bool(data.get("ok", False))
                ip = str(data.get("integration_path", "local_bridge"))
                pending = ip.endswith("_handoff_file") or ip in (
                    "claude_handoff_file",
                    "openclaw_handoff_file",
                    "cursor_handoff_file",
                )
                return ExecuteResult(
                    integration_path=ip,
                    ok=ok,
                    output=data.get("output"),
                    error=data.get("error"),
                    meta={
                        **{k: v for k, v in data.items() if k not in ("ok", "output", "error", "integration_path")},
                        "timeout_seconds": timeout_seconds,
                        "retry_limit": retry_limit,
                    },
                    pending_handoff=pending and ok,
                )
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            if attempt >= retry_limit:
                break
    return ExecuteResult(
        integration_path="local_bridge_unreachable",
        ok=False,
        output=None,
        error=last_error,
        meta={
            "url": url,
            "hint": "Start Local Bridge: apps/local-bridge (port 8010 default)",
            "timeout_seconds": timeout_seconds,
            "retry_limit": retry_limit,
        },
    )

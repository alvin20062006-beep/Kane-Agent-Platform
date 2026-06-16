"""
Kanaloa Action Gateway (P1): controlled orchestration without bypassing task/run/worker.

All mutating paths create audit + task_events via existing lifecycle stores.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from ..models import TaskAssignBody, TaskCreateBody
from ..store.repositories import agents_repo, local_bridge_repo, task_events_repo, tasks_repo
from .kanaloa_platform import (
    KANALOA_AGENT_ID,
    build_adapters_status_payload,
    build_agent_registry_entries,
    build_compact_snapshot_text,
)
from .permission_gate import Principal, assert_can_execute_external, get_kanaloa_principal, require_scope
from .runtime_audit import append_task_event, append_watchdog_issue
from .task_lifecycle import assign_task, cancel_task as lifecycle_cancel_task, create_task, run_task


def _audit(action: str, message: str, *, task_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
    append_watchdog_issue(
        f"kanaloa_action_{action}",
        message,
        severity="info",
        agent_id=KANALOA_AGENT_ID,
        source="watchdog",
        issue_status="resolved",
        recovery_hint=json.dumps(payload or {}, ensure_ascii=False)[:500],
    )
    if task_id:
        tt = tasks_repo.get(task_id)
        append_task_event(
            task_id,
            f"kanaloa_{action}",
            message[:400],
            correlation_id=tt.correlation_id if tt else None,
            payload=payload,
        )


def list_agents(principal: Principal) -> dict[str, Any]:
    require_scope(principal, "agents.list")
    items = [a.model_dump() for a in agents_repo.list()]
    _audit("list_agents", "Listed agents via Kanaloa gateway", payload={"count": len(items)})
    return {"ok": True, "items": items}


def get_agent_status(principal: Principal, agent_id: str) -> dict[str, Any]:
    require_scope(principal, "agents.read")
    agent = agents_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")
    bridge_rows = [x for x in local_bridge_repo.list() if x.agent_id == agent_id]
    _audit("get_agent_status", f"agent={agent_id}", payload={"bridge_rows": len(bridge_rows)})
    return {"ok": True, "agent": agent.model_dump(), "bridge_state": [b.model_dump() for b in bridge_rows]}


def list_adapters(principal: Principal) -> dict[str, Any]:
    require_scope(principal, "adapters.list")
    payload = build_adapters_status_payload()
    _audit("list_adapters", "Listed adapter status", payload={"keys": list(payload.keys())})
    return {"ok": True, "adapters": payload}


def check_adapter_status(principal: Principal, adapter_id: str) -> dict[str, Any]:
    require_scope(principal, "adapters.status")
    full = build_adapters_status_payload()
    mapping = {
        "claude_code": "claude_code",
        "cursor": "cursor",
        "openclaw": "openclaw_http",
        "openclaw_http": "openclaw_http",
        "local_bridge": "local_bridge",
    }
    key = mapping.get(adapter_id, adapter_id)
    block = full.get(key)
    if block is None:
        return {"ok": False, "error": "unknown_adapter", "adapter_id": adapter_id, "hint": list(mapping.keys())}
    _audit("check_adapter_status", f"adapter={adapter_id}", payload={"health": block.get("health")})
    return {"ok": True, "adapter_id": adapter_id, "status": block}


def create_agent_task(
    principal: Principal,
    *,
    agent_id: str,
    instruction: str,
    mode: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Create + assign; dry_run does not invoke run_task / worker."""
    require_scope(principal, "tasks.create")
    agent = agents_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    mode_n = (mode or "").strip().lower()
    if not mode_n:
        if principal.profile == "readonly":
            raise HTTPException(
                status_code=403,
                detail={"error": "readonly_profile", "message": "Cannot create tasks in readonly profile"},
            )
        mode_n = "execute" if principal.profile == "owner" else "dry_run"
    if mode_n not in {"dry_run", "execute"}:
        raise HTTPException(status_code=400, detail="invalid_mode")

    title = instruction.strip()[:120] or "Kanaloa task"
    prefix = "[KANALOA_MODE:dry_run]\n" if mode_n == "dry_run" else "[KANALOA_MODE:execute]\n"
    if workspace:
        prefix += f"[KANALOA_WORKSPACE:{workspace}]\n"
    desc = prefix + instruction.strip()

    if mode_n == "execute":
        assert_can_execute_external(principal, agent, workspace)

    task = create_task(
        TaskCreateBody(
            title=title,
            description=desc,
            execution_mode="direct_agent",
            queue_priority="normal",
        )
    )
    assign_task(task.task_id, TaskAssignBody(agent_id=agent_id))

    _audit(
        "create_agent_task",
        f"task={task.task_id} mode={mode_n} agent={agent_id}",
        task_id=task.task_id,
        payload={"mode": mode_n, "agent_id": agent_id},
    )

    if mode_n == "dry_run":
        return {
            "ok": True,
            "mode": "dry_run",
            "task_id": task.task_id,
            "assigned_agent_id": agent_id,
            "task_status": tasks_repo.get(task.task_id).status.value,
            "note": "Task created and assigned; worker not invoked (dry_run). Open /tasks/{task_id} for timeline.",
        }

    try:
        run_info = run_task(task.task_id)
        run_id = None
        if isinstance(run_info, dict) and run_info.get("run") is not None:
            run_id = getattr(run_info["run"], "run_id", None)
        _audit(
            "create_agent_task_execute",
            f"run queued task={task.task_id} run_id={run_id}",
            task_id=task.task_id,
            payload={"run_id": run_id},
        )
        return {
            "ok": True,
            "mode": "execute",
            "task_id": task.task_id,
            "task_status": tasks_repo.get(task.task_id).status.value,
            "run": run_info,
            "run_id": run_id,
            "note": "Worker queued this run; inspect task timeline and run logs.",
        }
    except HTTPException:
        _audit(
            "create_agent_task_execute_failed",
            f"task={task.task_id}",
            task_id=task.task_id,
            payload={"error": "run_task_failed"},
        )
        raise


def dispatch_agent_task(principal: Principal, task_id: str) -> dict[str, Any]:
    """Run an already-assigned external-agent task (respects permission + execute gates)."""
    require_scope(principal, "agents.dispatch")
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if not task.assigned_agent_id:
        raise HTTPException(status_code=400, detail="task_not_assigned")

    agent = agents_repo.get(task.assigned_agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent_not_found")

    ws = _workspace_from_task_description(task.description or "")
    assert_can_execute_external(principal, agent, ws)

    try:
        run_info = run_task(task_id)
        _audit("dispatch_agent_task", f"task={task_id}", task_id=task_id, payload={"ok": True})
        r_obj = run_info.get("run") if isinstance(run_info, dict) else None
        run_id = getattr(r_obj, "run_id", None) if r_obj else None
        return {
            "ok": True,
            "task_id": task_id,
            "run_id": run_id,
            "run": run_info,
            "task_status": tasks_repo.get(task_id).status.value,
        }
    except HTTPException as e:
        det = e.detail
        msg = json.dumps(det, ensure_ascii=False) if isinstance(det, dict) else str(det)
        _audit(
            "dispatch_agent_task_failed",
            msg,
            task_id=task_id,
            payload={"detail": msg},
        )
        raise


def _workspace_from_task_description(description: str | None) -> str | None:
    if not description:
        return None
    m = re.search(r"\[KANALOA_WORKSPACE:([^\]]+)\]", description)
    return m.group(1).strip() if m else None


def read_task_status(principal: Principal, task_id: str) -> dict[str, Any]:
    require_scope(principal, "tasks.read")
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return {"ok": True, "task": task.model_dump()}


def read_task_events(principal: Principal, task_id: str) -> dict[str, Any]:
    require_scope(principal, "tasks.read")
    if not tasks_repo.get(task_id):
        raise HTTPException(status_code=404, detail="task_not_found")
    events = [e.model_dump() for e in task_events_repo.list() if e.task_id == task_id]
    events.sort(key=lambda x: x.get("created_at") or "")
    require_scope(principal, "audit.read")
    return {"ok": True, "task_id": task_id, "events": events}


def cancel_agent_task(principal: Principal, task_id: str) -> dict[str, Any]:
    require_scope(principal, "tasks.cancel")
    task = lifecycle_cancel_task(task_id)
    _audit("cancel_task", f"cancelled {task_id}", task_id=task_id, payload={"status": task.status.value})
    return {"ok": True, "task_id": task_id, "task": task.model_dump()}


def first_enabled_claude_agent_id() -> str | None:
    for a in agents_repo.list():
        if (a.adapter_id or "") == "claude_code" and a.enabled:
            return a.agent_id
    return None


def first_coding_external_agent_id() -> str | None:
    """Prefer Claude Code, then other coding/external adapters."""
    order = ("claude_code", "cursor_cli", "openclaw_http", "local_script")
    for adapter in order:
        for a in agents_repo.list():
            if (
                a.enabled
                and a.type == "external"
                and (a.adapter_id or "") == adapter
            ):
                return a.agent_id
    return None


def format_agents_markdown() -> str:
    rows = build_agent_registry_entries()
    lines = ["### 平台已登记 Agent", ""]
    for r in rows:
        lines.append(
            f"- **{r['name']}** · `{r['id']}` · adapter=`{r.get('adapter')}` · enabled={r.get('enabled')} · status={r.get('status')}"
        )
    return "\n".join(lines)


def _status_question_keywords_present(t: str, tl: str) -> bool:
    if any(
        k in t
        for k in (
            "接上了吗",
            "连接了吗",
            "连上了吗",
            "可用吗",
            "能用吗",
            "配置了吗",
        )
    ):
        return True
    if "状态" in t:
        return True
    if "adapter" in tl or "适配器" in t:
        return True
    return False


def _status_query_adapter_key(t: str, tl: str) -> str | None:
    if re.search(r"\bcursor\b", tl):
        return "cursor"
    if "claude" in tl:
        return "claude_code"
    return None


def _has_task_like_intent_besides_status(t: str) -> bool:
    """Avoid treating repair/run/check-project asks as pure adapter pings."""
    return bool(re.search(r"(修复|改正|运行测试|跑测试|创建任务|执行代码|排查项目|检查项目|检查仓库)", t))


def _is_pure_adapter_status_query(user_text: str) -> bool:
    """
    Short connectivity questions (Claude Code / Cursor) — must not enqueue tasks.
    """
    t = user_text.strip()
    tl = t.lower()
    key = _status_query_adapter_key(t, tl)
    if not key:
        return False
    if not _status_question_keywords_present(t, tl):
        return False
    if _has_task_like_intent_besides_status(t):
        return False
    return True


def _format_adapter_status_markdown(principal: Principal, adapter_key: str) -> str:
    st = check_adapter_status(principal, adapter_key)
    label = "Claude Code" if adapter_key == "claude_code" else "Cursor"
    if not st.get("ok"):
        return (
            f"### {label} 适配器\n\n"
            f"查询失败：`{st.get('error', 'unknown')}`\n"
        )
    j = st.get("status") or {}
    lines = [
        f"### {label} 适配器状态",
        "",
        f"- **health**: `{j.get('health', '—')}`",
        f"- **configured**: {j.get('configured')}",
        f"- **available**: {j.get('available')}",
    ]
    det = j.get("details")
    if det:
        lines.append(f"- **details**: {det}")
    if j.get("health") in ("unsupported", "not_configured") or j.get("available") is False:
        lines.append("")
        lines.append("_状态由平台实时探测；不可用不会冒充已连接。_")
    lines.append("")
    lines.append("（本回复仅查询 adapter 状态，未创建平台任务。）")
    return "\n".join(lines)


def list_recent_tasks(principal: Principal, *, limit: int = 8) -> dict[str, Any]:
    """Recent tasks (newest first) for orchestrator / UI; no secret payload."""
    require_scope(principal, "tasks.read")
    lim = max(1, min(limit, 32))
    rows = sorted(
        tasks_repo.list(),
        key=lambda x: x.updated_at or x.created_at or "",
        reverse=True,
    )[:lim]
    items = [
        {
            "task_id": tk.task_id,
            "title": tk.title,
            "status": tk.status.value,
            "assigned_agent_id": tk.assigned_agent_id,
            "created_at": tk.created_at,
            "updated_at": tk.updated_at,
        }
        for tk in rows
    ]
    _audit("list_recent_tasks", f"count={len(items)}", payload={"limit": lim})
    return {"ok": True, "items": items}


def _is_connect_agent_intent(text: str, tl: str) -> bool:
    if re.search(r"连接.{0,16}(agent|智能体|外部)", text, re.I):
        return True
    if re.search(r"connect.{0,16}(agent|http|webhook)", tl, re.I):
        return True
    if "帮我连接" in text and re.search(r"agent|智能体|http", text, re.I):
        return True
    return False


def _format_connect_agent_guide_markdown() -> str:
    from ..models import SkillExecuteBody
    from .skills.connect_agent_skill import execute_connect_agent_skill

    guide = execute_connect_agent_skill({"step": "guide"}, SkillExecuteBody(input={"step": "guide"}))
    probe = execute_connect_agent_skill({"step": "probe"}, SkillExecuteBody(input={"step": "probe"}))
    lines = [
        "### 连接外部 Agent",
        "",
        "推荐通过 **连接向导** 完成（约 5–10 分钟），无需阅读 EXTERNAL_AGENT_INTEGRATION.md。",
        "",
        "在 Web 打开：**Local Bridge → 连接外部 Agent**（`/local-bridge?connect=1`）。",
        "",
    ]
    if probe.output and probe.output.get("natural_language"):
        lines.append(f"**探测**：{probe.output['natural_language']}")
        lines.append("")
    if guide.output and guide.output.get("steps"):
        lines.append("**步骤概览**：")
        for i, step in enumerate(guide.output["steps"], start=1):
            lines.append(f"{i}. **{step.get('title', '')}** — {step.get('detail', '')}")
    lines.append("")
    lines.append("默认从 **HTTP/Webhook 通用 Agent** 开始；未填 URL 时自动走 handoff + callback。")
    return "\n".join(lines)


def try_chat_actions(user_text: str) -> str | None:
    """
    Owner-intent router (deterministic): execute by default for owner profile unless user asks dry_run.
    """
    principal = get_kanaloa_principal()
    t = user_text.strip()
    tl = t.lower()

    if _is_connect_agent_intent(t, tl):
        return _format_connect_agent_guide_markdown()

    if principal.profile == "readonly":
        if re.search(r"(创建任务|execute|dispatch|修复项目)", tl):
            return (
                "### 权限模式：readonly\n\n"
                "当前 `KANE_PERMISSION_PROFILE=readonly`，Kanaloa 仅允许查看列表与状态，"
                "不会创建任务或执行外部 Agent。若这是你的私有部署，请将 profile 设为 **owner**。"
            )

    if _is_pure_adapter_status_query(t):
        ak = _status_query_adapter_key(t, tl)
        if ak:
            return _format_adapter_status_markdown(principal, ak)

    if re.search(r"(有哪些|列出).{0,6}(agent|Agent|智能体)", t) or re.search(
        r"list\s+agents", tl, re.I
    ):
        return format_agents_markdown() + "\n\n（registry 实时数据）"

    master_like = "总任务" in t or bool(re.search(r"\bmaster\s*task\b", tl))
    if (re.search(r"(刚才|最近|上一个).{0,10}(任务|task)", t) or "recent task" in tl) and not master_like:
        rows = sorted(
            tasks_repo.list(),
            key=lambda x: x.updated_at or x.created_at or "",
            reverse=True,
        )[:6]
        lines = ["### 最近任务（节选）", ""]
        for tk in rows:
            lines.append(f"- `{tk.task_id}` · **{tk.status.value}** · {tk.title[:80]}")
        return "\n".join(lines) if rows else "### 暂无任务记录"

    cancel_intent = bool(
        re.search(r"(取消|撤销).{0,24}(任务|task)", t, re.I)
        or re.search(r"\b(cancel|abort)\b.{0,20}\b(task)\b", tl, re.I)
        or ("取消" in t and bool(re.search(r"(刚才|上一个|最近|这条).{0,8}任务", t)))
    )
    if cancel_intent:
        if principal.profile == "readonly":
            return (
                "### 权限模式：readonly\n\n"
                "当前无法通过 Kanaloa 取消任务。请将 `KANE_PERMISSION_PROFILE` 设为 **owner** 或 **safe**。"
            )
        rows = sorted(
            tasks_repo.list(),
            key=lambda x: x.updated_at or x.created_at or "",
            reverse=True,
        )
        if not rows:
            return "### 没有可取消的任务\n\n任务列表为空。"
        tid = rows[0].task_id
        try:
            out = cancel_agent_task(principal, tid)
            return (
                "### 已请求取消任务（最近更新的一条）\n\n"
                f"- **task_id**: `{out['task_id']}`\n"
                f"- **status**: `{out['task'].get('status', '—')}`\n\n"
                "请在 **任务** 页确认时间线与最终状态。\n"
            )
        except HTTPException as e:
            detail = e.detail
            msg = json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else str(detail)
            return f"### 无法取消该任务\n\n{msg}\n"

    explicit_dry = any(
        [
            "dry_run" in tl,
            "dry run" in tl,
            "演练" in t,
            "预演" in t,
            "不要执行" in t,
            "别执行" in t,
            "只做计划" in t,
            "先模拟" in t,
            "只检查不修改" in t,
            "只检查" in t and "不修改" in t,
            bool(re.search(r"\bplan only\b|\bsimulate only\b", tl)),
        ]
    )
    explicit_exec = ("执行" in t and ("Claude" in t or "claude" in tl)) or (
        re.search(r"\bexecute\s+claude", tl) is not None
    )

    has_claude = "claude" in tl or "claude code" in tl
    wants_task = (
        explicit_dry
        or explicit_exec
        or has_claude
        or bool(re.search(r"(修复|改正)", t))
        or bool(re.search(r"(检查|排查).{0,16}(项目|仓库|代码|测试)", t))
        or bool(re.search(r"(跑|运行).{0,8}测试", t))
    )
    if not wants_task:
        return None

    if explicit_dry:
        mode = "dry_run"
    elif principal.profile == "owner":
        mode = "execute"
    elif principal.profile == "safe":
        mode = "execute" if explicit_exec else "dry_run"
    else:
        mode = "dry_run"

    agent_id = first_enabled_claude_agent_id() if has_claude else None
    if not agent_id:
        agent_id = first_coding_external_agent_id()
    if not agent_id:
        snap = build_compact_snapshot_text()
        return (
            "### 未找到可用的外部 Coding Agent\n"
            "（依次尝试 `claude_code` / `cursor_cli` / `openclaw_http` / `local_script`）。"
            "请在 **Agents** 中添加并启用至少一个。\n\n"
            f"```json\n{snap[:3500]}\n```\n"
        )
    try:
        out = create_agent_task(
            principal,
            agent_id=agent_id,
            instruction=t,
            mode=mode,
            workspace=None,
        )
        return (
            f"### Kanaloa 已创建任务（**{out['mode']}**）\n\n"
            f"- **task_id**: `{out['task_id']}`\n"
            f"- **status**: `{out.get('task_status', '—')}`\n"
            f"- **run_id**: `{out.get('run_id') or '（dry_run 未排队 run）'}`\n\n"
            f"{out.get('note', '')}\n\n"
            "在 **任务** 页打开该 ID 可查看事件与 run 日志。\n"
        )
    except HTTPException as e:
        detail = e.detail
        if isinstance(detail, dict):
            msg = json.dumps(detail, ensure_ascii=False)
        else:
            msg = str(detail)
        return (
            "### Kanaloa 无法执行该请求\n\n"
            f"{msg}\n\n"
            "- **owner**：外部 execute 一般可直接排队；若设置了 `OCTOPUS_KANALOA_WORKSPACE_ALLOWLIST`，工作区须在内。\n"
            "- **safe**：还需 `OCTOPUS_KANALOA_ADAPTER_EXECUTE=1`。\n"
            "- **readonly**：不会创建或执行任务。\n"
            "- **dry_run**：仅创建并指派，不触发 worker。\n"
        )

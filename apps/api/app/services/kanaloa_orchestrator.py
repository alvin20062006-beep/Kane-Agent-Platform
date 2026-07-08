"""
Kanaloa P3 Orchestrator Runtime — master task, subtasks, dispatch, observe, retry, verify.

Execution flows through kanaloa_actions (tasks/worker/adapters). LLM is only used for JSON plans.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from fastapi import HTTPException

from ..id_utils import new_id
from ..models import OrchestratorMasterTask, OrchestratorSubtaskRecord, Task, TaskStatus
from ..settings_env import (
    get_kanaloa_orchestrator_max_attempts_per_subtask,
    get_kanaloa_orchestrator_max_runtime_seconds,
    get_kanaloa_orchestrator_max_subtasks,
    get_kanaloa_orchestrator_observe_max_wait_seconds,
    get_kanaloa_orchestrator_observe_poll_seconds,
)
from ..store.repositories import master_tasks_repo, tasks_repo
from .agent_capability_matcher import select_agent_for_kind
from .kanaloa_actions import cancel_agent_task, create_agent_task
from .kanaloa_observer import observe_platform_task, sanitize_text, summarize_observation_for_subtask, terminal_status
from .permission_gate import Principal, get_kanaloa_principal
from .runtime_audit import append_watchdog_issue, now_iso
from .verification_runner import build_verification_subtask_specs, verification_record_template


def _emit_audit(master: OrchestratorMasterTask, typ: str, message: str, payload: dict[str, Any] | None = None) -> None:
    entry = {"type": typ, "message": message, "payload": payload or {}, "created_at": now_iso()}
    master.events.append(entry)
    append_watchdog_issue(
        typ,
        message,
        severity="info",
        issue_status="resolved",
        recovery_hint=json.dumps(payload or {}, ensure_ascii=False)[:500],
        source="watchdog",
    )


def _extract_json_array(text: str) -> list[dict[str, Any]] | None:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError:
        return None
    return None


def plan_subtasks_llm(user_instruction: str, max_items: int) -> list[dict[str, Any]] | None:
    try:
        from .llm_client import LLMNotConfiguredError, call_llm

        sys = (
            "You output ONLY a JSON array (no markdown). Each element: "
            '{"id":"string","kind":"code_audit|code_fix|verification|summarize|repo_status|frontend_check|external_http_task|cursor_task|unknown",'
            '"title":"string","instruction":"string","command_key":"optional string for verification"}. '
            f"Max {max_items} items. Do not include secrets."
        )
        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user_instruction[:8000]},
        ]
        raw = call_llm(messages)
        arr = _extract_json_array(raw)
        if not arr:
            return None
        return arr[:max_items]
    except LLMNotConfiguredError:
        return None
    except Exception:
        return None


def heuristic_subtasks(user_instruction: str, max_items: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if len(user_instruction.strip()) < 3:
        return rows
    rows.append(
        {
            "id": new_id("plan"),
            "kind": "code_audit",
            "title": "Repository audit",
            "instruction": user_instruction[:8000],
        }
    )
    rows.extend(build_verification_subtask_specs(user_instruction))
    rows.append(
        {
            "id": new_id("plan"),
            "kind": "summarize",
            "title": "Summarize results",
            "instruction": "Provide a concise summary of orchestration outcomes and next steps.",
        }
    )
    return rows[:max_items]


def normalize_plan_entries(raw: list[dict[str, Any]], master_task_id: str, max_items: int) -> list[OrchestratorSubtaskRecord]:
    ts = now_iso()
    out: list[OrchestratorSubtaskRecord] = []
    for i, row in enumerate(raw[:max_items]):
        sid = str(row.get("id") or new_id("osub"))
        kind = str(row.get("kind") or "unknown").lower()
        title = str(row.get("title") or f"Step {i+1}")[:200]
        instr = str(row.get("instruction") or row.get("prompt") or "")[:19000]
        ck = row.get("command_key")
        out.append(
            OrchestratorSubtaskRecord(
                subtask_id=sid,
                master_task_id=master_task_id,
                title=title,
                instruction=instr or title,
                kind=kind,
                command_key=str(ck) if ck else None,
                created_at=ts,
                updated_at=ts,
            )
        )
    return out


def create_master_task_skeleton(user_instruction: str, *, conversation_id: str | None) -> OrchestratorMasterTask:
    mid = new_id("master")
    corr = new_id("corr")
    ts = now_iso()
    return OrchestratorMasterTask(
        master_task_id=mid,
        user_instruction=user_instruction.strip(),
        status="pending",
        correlation_id=corr,
        conversation_id=conversation_id,
        created_at=ts,
        updated_at=ts,
    )


def plan_and_attach_subtasks(master: OrchestratorMasterTask) -> OrchestratorMasterTask:
    mx = get_kanaloa_orchestrator_max_subtasks()
    planned = plan_subtasks_llm(master.user_instruction, mx)
    if not planned:
        planned = heuristic_subtasks(master.user_instruction, mx)
    master.subtasks = normalize_plan_entries(planned, master.master_task_id, mx)
    master.updated_at = now_iso()
    master_tasks_repo.upsert(master)
    _emit_audit(master, "KANALOA_SUBTASK_CREATED", f"count={len(master.subtasks)}", {"count": len(master.subtasks)})
    return master


def create_master_task(user_instruction: str, *, conversation_id: str | None = None) -> OrchestratorMasterTask:
    master = create_master_task_skeleton(user_instruction, conversation_id=conversation_id)
    master_tasks_repo.upsert(master)
    _emit_audit(master, "KANALOA_MASTER_TASK_CREATED", master.master_task_id, {"instruction_len": len(user_instruction)})
    plan_and_attach_subtasks(master)
    return master_tasks_repo.get(master.master_task_id) or master


def _poll_terminal(task_id: str, *, mode_execute: bool) -> tuple[str, str | None]:
    if not mode_execute:
        return ("assigned", None)
    deadline = time.monotonic() + get_kanaloa_orchestrator_observe_max_wait_seconds()
    poll = get_kanaloa_orchestrator_observe_poll_seconds()
    last_rid: str | None = None
    while time.monotonic() < deadline:
        t = tasks_repo.get(task_id)
        if not t:
            return ("failed", None)
        last_rid = t.last_run_id or last_rid
        if terminal_status(t.status):
            return (t.status.value, last_rid)
        time.sleep(poll)
    return ("blocked", last_rid)


def run_subtask_with_retries(
    master: OrchestratorMasterTask,
    sub: OrchestratorSubtaskRecord,
    principal: Principal,
    *,
    subtask_mode: str,
) -> None:
    agent_id, adapter_id, evidence = select_agent_for_kind(sub.kind)
    sub.target_agent_id = agent_id
    sub.target_adapter_id = adapter_id
    sub.updated_at = now_iso()
    master.selected_agents[sub.subtask_id] = agent_id or ""
    _emit_audit(
        master,
        "KANALOA_AGENT_SELECTED",
        sub.subtask_id,
        {"agent_id": agent_id, "adapter_id": adapter_id, "kind": sub.kind},
    )

    if not agent_id:
        sub.status = "blocked"
        sub.error = sanitize_text(json.dumps(evidence, ensure_ascii=False), 800)
        sub.updated_at = now_iso()
        _emit_audit(master, "KANALOA_SUBTASK_OBSERVED", sub.subtask_id, {"blocked": True, "evidence_keys": list(evidence.keys())})
        return

    max_att = get_kanaloa_orchestrator_max_attempts_per_subtask()
    mode_exec = subtask_mode == "execute" and principal.profile != "readonly"

    for attempt in range(max_att):
        sub.attempt_count = attempt + 1
        sub.status = "running"
        sub.updated_at = now_iso()
        master.updated_at = now_iso()
        master_tasks_repo.upsert(master)

        try:
            out = create_agent_task(
                principal,
                agent_id=agent_id,
                instruction=sub.instruction,
                mode="execute" if mode_exec else "dry_run",
                workspace=None,
            )
        except HTTPException as e:
            sub.error = str(e.detail)
            _emit_audit(master, "KANALOA_SUBTASK_OBSERVED", sub.subtask_id, {"http_error": True})
            if attempt + 1 < max_att:
                _emit_audit(master, "KANALOA_SUBTASK_RETRIED", sub.subtask_id, {"attempt": attempt + 1})
                continue
            sub.status = "failed"
            sub.updated_at = now_iso()
            return

        sub.platform_task_id = out.get("task_id")
        sub.last_run_id = out.get("run_id") if isinstance(out.get("run_id"), str) else None
        _emit_audit(
            master,
            "KANALOA_SUBTASK_DISPATCHED",
            sub.subtask_id,
            {"task_id": sub.platform_task_id, "run_id": sub.last_run_id, "mode": out.get("mode")},
        )

        st, rid = _poll_terminal(sub.platform_task_id or "", mode_execute=mode_exec)
        sub.last_run_id = rid or sub.last_run_id
        summary = summarize_observation_for_subtask(sub.platform_task_id, rid)
        sub.result_summary = sanitize_text(summary, 1500)
        _emit_audit(master, "KANALOA_SUBTASK_OBSERVED", sub.subtask_id, {"terminal": st})

        if st == "succeeded" or (not mode_exec and bool(sub.platform_task_id)):
            sub.status = "completed"
            sub.updated_at = now_iso()
            if attempt > 0:
                _emit_audit(master, "KANALOA_SUBTASK_RETRIED", sub.subtask_id, {"attempts": sub.attempt_count})
            return

        if attempt + 1 < max_att:
            _emit_audit(master, "KANALOA_SUBTASK_RETRIED", sub.subtask_id, {"attempt": attempt + 1})
            continue

        sub.status = "failed" if st == "failed" else "blocked"
        sub.error = st
        sub.updated_at = now_iso()
        return


def resolve_verification_record(sub: OrchestratorSubtaskRecord) -> dict[str, Any]:
    """Map verification subtask + platform Task to honest phases (never 'passed' without succeeded task)."""
    cmd = sub.command_key
    tid = sub.platform_task_id
    err = sub.error
    if not tid:
        return verification_record_template(
            command_key=cmd,
            command=cmd,
            status="blocked",
            verification_phase="blocked",
            exit_code=None,
            output_summary=sub.result_summary,
            error_summary=err or "verification_task_not_created_or_dispatch_blocked",
            platform_task_id=None,
            platform_task_status=None,
        )
    tk: Task | None = tasks_repo.get(tid)
    if not tk:
        return verification_record_template(
            command_key=cmd,
            command=cmd,
            status="failed",
            verification_phase="failed",
            exit_code=None,
            output_summary=None,
            error_summary="platform_task_record_missing",
            platform_task_id=tid,
            platform_task_status=None,
        )
    pst = tk.status
    pv = pst.value
    if pst == TaskStatus.succeeded:
        vphase = "passed"
        st_line = "completed"
    elif pst in (TaskStatus.failed, TaskStatus.cancelled, TaskStatus.expired):
        vphase = "failed"
        st_line = "failed"
    elif pst in (TaskStatus.queued, TaskStatus.created, TaskStatus.assigned):
        vphase = "queued"
        st_line = "queued"
    elif pst == TaskStatus.running:
        vphase = "running"
        st_line = "running"
    elif pst in (TaskStatus.waiting_approval, TaskStatus.stalled):
        vphase = "blocked"
        st_line = "blocked"
    else:
        vphase = pv
        st_line = pv
    return verification_record_template(
        command_key=cmd,
        command=cmd,
        status=st_line,
        verification_phase=vphase,
        exit_code=None,
        output_summary=sub.result_summary,
        error_summary=tk.last_error or err,
        platform_task_id=tid,
        platform_task_status=pv,
    )


def run_verification_summary(master: OrchestratorMasterTask) -> None:
    _emit_audit(master, "KANALOA_VERIFICATION_STARTED", master.master_task_id, {})
    results: list[dict[str, Any]] = []
    for sub in master.subtasks:
        if sub.kind != "verification":
            continue
        results.append(resolve_verification_record(sub))
    master.verification_results = results
    if results:
        if any(r.get("verification_phase") == "failed" for r in results):
            master.verification_status = "failed"
        elif all(r.get("verification_phase") == "passed" for r in results):
            master.verification_status = "passed"
        elif any(r.get("verification_phase") == "passed" for r in results):
            master.verification_status = "partial"
        else:
            master.verification_status = "incomplete"
    else:
        master.verification_status = "skipped"
    _emit_audit(master, "KANALOA_VERIFICATION_COMPLETED", master.master_task_id, {"count": len(results)})
    master.updated_at = now_iso()


def summarize_run(master: OrchestratorMasterTask) -> str:
    lines = [
        f"Master task `{master.master_task_id}` status={master.status}",
        f"Instruction: {master.user_instruction[:400]}",
        "",
        "Subtasks:",
    ]
    for s in master.subtasks:
        lines.append(
            f"- [{s.status}] {s.title} agent={s.target_agent_id or '—'} "
            f"task_id={s.platform_task_id or '—'} run_id={s.last_run_id or '—'} attempts={s.attempt_count}"
        )
        if s.result_summary:
            lines.append(f"  summary: {s.result_summary[:240]}")
    if master.verification_results:
        lines.append("")
        lines.append("Verification (worker/bridge — not API-local shell):")
        for vr in master.verification_results:
            vk = vr.get("command_key") or "—"
            vp = vr.get("verification_phase") or vr.get("status")
            ptid = vr.get("platform_task_id") or "—"
            pts = vr.get("platform_task_status") or "—"
            lines.append(f"- **{vk}**: verification_phase={vp} · platform_task=`{ptid}` · platform_status={pts}")
            if vr.get("error_summary"):
                lines.append(f"  note: {str(vr.get('error_summary'))[:220]}")
        lines.append("")
        lines.append("Verification outcome (plain language):")
        for vr in master.verification_results:
            vk = vr.get("command_key") or "—"
            vp = str(vr.get("verification_phase") or vr.get("status") or "")
            if vp == "passed":
                lines.append(f"- **{vk}**: verification completed — platform task **passed**.")
            elif vp == "queued":
                lines.append(
                    f"- **{vk}**: verification task created — still **queued** (not passed until worker succeeds)."
                )
            elif vp == "running":
                lines.append(f"- **{vk}**: verification **running**.")
            elif vp == "blocked":
                lines.append(f"- **{vk}**: verification **blocked** (stall / dependency / gate).")
            elif vp == "failed":
                lines.append(f"- **{vk}**: verification **failed**.")
            elif vp == "completed":
                lines.append(f"- **{vk}**: verification **completed** (see platform_task_status above).")
            else:
                lines.append(f"- **{vk}**: verification state **{vp}**.")
    master.final_summary = "\n".join(lines)
    master.updated_at = now_iso()
    return master.final_summary


def execute_master_run(
    master_task_id: str,
    principal: Principal | None = None,
    *,
    subtask_mode: str = "execute",
) -> OrchestratorMasterTask:
    principal = principal or get_kanaloa_principal()
    if principal.profile == "readonly":
        raise HTTPException(status_code=403, detail={"error": "readonly_profile", "message": "Orchestrator disabled"})

    master = master_tasks_repo.get(master_task_id)
    if not master:
        raise HTTPException(status_code=404, detail="master_task_not_found")

    master.status = "running"
    master.started_run_at = master.started_run_at or now_iso()
    master.updated_at = now_iso()
    master_tasks_repo.upsert(master)

    started = time.monotonic()
    max_rt = get_kanaloa_orchestrator_max_runtime_seconds()

    for sub in master.subtasks:
        if time.monotonic() - started > max_rt:
            master.status = "blocked"
            _emit_audit(master, "KANALOA_MASTER_TASK_FAILED", master.master_task_id, {"reason": "runtime_cap"})
            break
        if sub.status in {"completed", "skipped"}:
            continue
        run_subtask_with_retries(master, sub, principal, subtask_mode=subtask_mode)
        master_tasks_repo.upsert(master)
        master = master_tasks_repo.get(master_task_id) or master

    if master.status == "running":
        failed = [s for s in master.subtasks if s.status in {"failed", "blocked"}]
        master.status = "failed" if failed else "completed"
        if master.status == "completed":
            _emit_audit(master, "KANALOA_MASTER_TASK_COMPLETED", master.master_task_id, {})
        else:
            _emit_audit(master, "KANALOA_MASTER_TASK_FAILED", master.master_task_id, {"failed_subtasks": len(failed)})

    run_verification_summary(master)
    summarize_run(master)
    master.completed_at = now_iso()
    master.updated_at = now_iso()
    master_tasks_repo.upsert(master)
    return master


def continue_master_task(master_task_id: str, principal: Principal | None = None, *, subtask_mode: str = "execute") -> OrchestratorMasterTask:
    """Resume execution for pending/blocked/failed subtasks."""
    return execute_master_run(master_task_id, principal, subtask_mode=subtask_mode)


def cancel_master_task(master_task_id: str, principal: Principal | None = None) -> OrchestratorMasterTask:
    principal = principal or get_kanaloa_principal()
    if principal.profile == "readonly":
        raise HTTPException(status_code=403, detail="readonly_profile")

    master = master_tasks_repo.get(master_task_id)
    if not master:
        raise HTTPException(status_code=404, detail="master_task_not_found")

    for sub in master.subtasks:
        tid = sub.platform_task_id
        if not tid:
            continue
        t = tasks_repo.get(tid)
        if t and not terminal_status(t.status):
            try:
                cancel_agent_task(principal, tid)
            except HTTPException:
                pass
        sub.status = "skipped"
        sub.updated_at = now_iso()

    master.status = "cancelled"
    master.updated_at = now_iso()
    master.completed_at = now_iso()
    _emit_audit(master, "KANALOA_MASTER_TASK_CANCELLED", master_task_id, {})
    master_tasks_repo.upsert(master)
    return master


def list_recent_masters(*, limit: int = 12) -> list[OrchestratorMasterTask]:
    rows = master_tasks_repo.list()
    rows.sort(key=lambda m: m.updated_at or m.created_at or "", reverse=True)
    return rows[:limit]


def get_latest_master_for_conversation(conversation_id: str | None) -> OrchestratorMasterTask | None:
    if not conversation_id:
        return None
    for m in list_recent_masters(limit=64):
        if m.conversation_id == conversation_id:
            return m
    return None


def orchestrator_run_pipeline(
    *,
    instruction: str,
    conversation_id: str | None,
    subtask_mode: str,
) -> OrchestratorMasterTask:
    principal = get_kanaloa_principal()
    master = create_master_task(instruction, conversation_id=conversation_id)
    return execute_master_run(master.master_task_id, principal, subtask_mode=subtask_mode)


def run_master_task_background(master_task_id: str, subtask_mode: str) -> None:
    """BackgroundTasks / thread entry: runs execute_master_run; persists failure on exception."""
    try:
        principal = get_kanaloa_principal()
        execute_master_run(master_task_id, principal, subtask_mode=subtask_mode)
    except HTTPException as e:
        det = e.detail
        msg = json.dumps(det, ensure_ascii=False) if isinstance(det, dict) else str(det)
        _fail_master_async(master_task_id, msg[:1200])
    except Exception as e:  # noqa: BLE001
        _fail_master_async(master_task_id, str(e)[:1200])


def _fail_master_async(master_task_id: str, err: str) -> None:
    master = master_tasks_repo.get(master_task_id)
    if not master:
        return
    master.status = "failed"
    master.updated_at = now_iso()
    master.events.append(
        {
            "type": "KANALOA_MASTER_TASK_FAILED",
            "message": master_task_id,
            "payload": {"reason": "background_failure", "error": err},
            "created_at": now_iso(),
        }
    )
    master_tasks_repo.upsert(master)


def orchestrator_begin_run(
    *,
    instruction: str,
    conversation_id: str | None,
    subtask_mode: str,
) -> OrchestratorMasterTask:
    """Create master task and mark queued; caller schedules run_master_task_background."""
    master = create_master_task(instruction, conversation_id=conversation_id)
    m = master_tasks_repo.get(master.master_task_id)
    if m:
        m.status = "queued"
        m.updated_at = now_iso()
        master_tasks_repo.upsert(m)
    return master_tasks_repo.get(master.master_task_id) or master


def schedule_orchestrator_run_thread(master_task_id: str, subtask_mode: str) -> None:
    """Fire-and-forget from non-FastAPI contexts (e.g. Kanaloa chat)."""
    t = threading.Thread(
        target=run_master_task_background,
        args=(master_task_id, subtask_mode),
        name=f"kanaloa-orchestrator-{master_task_id}",
        daemon=True,
    )
    t.start()


def get_master_task(master_task_id: str) -> OrchestratorMasterTask | None:
    return master_tasks_repo.get(master_task_id)


def is_master_task_result_query(text: str) -> bool:
    """User asks for orchestrator master task outcome — not generic platform task list."""
    t = text.strip()
    tl = t.lower()
    if re.search(r"(查看|显示).{0,16}master\s*task", tl):
        return True
    if re.search(r"\bmaster\s*task\b", tl) and any(
        k in tl for k in ("result", "status", "summary", "how", "what")
    ):
        return True
    if "查看" in t and "总任务" in t:
        return True
    if "总任务" in t and any(x in t for x in ("结果", "怎么样", "如何", "状态")):
        return True
    if "刚才" in t and "总任务" in t and any(x in t for x in ("结果", "怎么样", "如何", "状态")):
        return True
    return False


def format_master_task_markdown(master: OrchestratorMasterTask) -> str:
    lines = [
        "### 总任务（Master Task）状态",
        "",
        f"- **master_task_id**: `{master.master_task_id}`",
        f"- **status**: **{master.status}**",
        f"- **verification_status**: {master.verification_status or '—'}",
        "",
        "**Subtasks:**",
    ]
    for s in master.subtasks:
        lines.append(
            f"- `{s.subtask_id}` · **{s.status}** · {s.title[:80]} · "
            f"platform_task=`{s.platform_task_id or '—'}` · attempts={s.attempt_count}"
        )
    if master.final_summary:
        lines.extend(["", "**final_summary:**", master.final_summary[:6000]])
    else:
        lines.extend(["", "_No final_summary yet._"])
    return "\n".join(lines)


def try_master_task_query_reply(user_text: str, conversation_id: str | None) -> str | None:
    if not is_master_task_result_query(user_text.strip()):
        return None
    if not conversation_id:
        return (
            "### 总任务查询\n\n需要会话上下文才能关联本对话的 master task。"
            "若通过 HTTP API 调用编排，请传入 `conversation_id`。"
        )
    m = get_latest_master_for_conversation(conversation_id)
    if not m:
        return "### 暂无总任务记录\n\n本对话下尚未创建关联的 master task。"
    m2 = master_tasks_repo.get(m.master_task_id) or m
    return format_master_task_markdown(m2)


def is_complex_orchestrator_request(text: str) -> bool:
    t = text.strip()
    if len(t) > 140 and ("测试" in t or "test" in t.lower()) and ("修复" in t or "检查" in t or "audit" in t.lower()):
        return True
    if re.search(r"(检查|审计|排查).{0,40}(项目|仓库|平台).{0,50}(测试|跑|build)", t):
        return True
    if "多个" in t and ("agent" in t.lower() or "智能体" in t):
        return True
    if re.search(r"\borchestrator\b", t, re.I):
        return True
    return False


def is_continue_master_request(text: str) -> bool:
    t = text.strip()
    return bool(re.search(r"(继续|接着|恢复).{0,20}(总任务|编排|master|orchestrator)", t, re.I)) or bool(
        re.search(r"(继续|接着).{0,12}刚才.{0,8}总任务", t)
    )


def try_orchestrator_chat(user_text: str, conversation_id: str | None) -> str | None:
    """
    Multi-step orchestration for complex engineering asks; uses persisted master tasks for continuity.
    Returns None to fall through to P2 try_chat_actions / LLM.
    """
    q = try_master_task_query_reply(user_text, conversation_id)
    if q:
        return q

    if is_continue_master_request(user_text.strip()):
        prev = get_latest_master_for_conversation(conversation_id)
        if prev:
            schedule_orchestrator_run_thread(prev.master_task_id, "execute")
            return (
                "### 编排继续已提交（后台执行）\n\n"
                f"- **master_task_id**: `{prev.master_task_id}`\n"
                "- 请在 **编排** 页或通过 `GET /api/kanaloa/orchestrator/tasks/{{id}}` 轮询状态与 final_summary。\n"
            )
        return None

    if not is_complex_orchestrator_request(user_text.strip()):
        return None

    try:
        m = orchestrator_begin_run(
            instruction=user_text.strip(),
            conversation_id=conversation_id,
            subtask_mode="execute",
        )
        schedule_orchestrator_run_thread(m.master_task_id, "execute")
        return (
            "### Kanaloa 编排已提交（后台执行）\n\n"
            f"- **master_task_id**: `{m.master_task_id}`\n"
            "- 后台运行完成后可通过编排 API 或编排页查看结果。\n"
        )
    except HTTPException as e:
        detail = e.detail
        msg = json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else str(detail)
        return f"### 编排执行受限\n\n{msg}"

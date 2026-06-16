from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query

from ...pagination import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_TIMELINE_EVENTS_LIMIT,
    DEFAULT_TIMELINE_LOGS_LIMIT,
    MAX_TIMELINE_EVENTS_LIMIT,
    MAX_TIMELINE_LOGS_LIMIT,
    paginate,
)
from ...store.run_log_queries import list_logs_for_run

from ...models import (
    ConversationCreateBody,
    ConversationMessageBody,
    ConversationPatchBody,
    ConversationPromoteBody,
    AdvisorSuggestion,
    ExecutionPolicyUpsertBody,
    EscalationActionBody,
    AgentApiBindingBody,
    AgentApiProfileUpsertBody,
    AgentCreateBody,
    AgentPatchBody,
    FileArtifact,
    FileArtifactCreateBody,
    GovernorEvaluateBody,
    NotificationChannelUpsertBody,
    ListResponse,
    ClaudeAdapterDispatchBody,
    KanaloaCancelBody,
    KanaloaCreateTaskBody,
    KanaloaDispatchBody,
    KanaloaOrchestratorContinueBody,
    KanaloaOrchestratorRunBody,
    LocalBridgeRegisterBody,
    LocalBridgeResultBody,
    TaskAssignBody,
    TaskApproveBody,
    TaskCreateBody,
    TaskFailBody,
    TaskRejectBody,
    SkillExecuteBody,
    SkillPatchBody,
    CredentialUpsertBody,
)
from ...services.escalations import list_escalations, update_escalation
from ...services.governor import (
    build_and_evaluate,
    confirm_decision,
    get_decision,
    get_governor_summary,
    list_decisions,
)
from ...services.advisor import (
    accept_advisor_suggestion,
    build_advisor_summary,
    build_task_advice,
    dismiss_advisor_suggestion,
    list_advisor_suggestions,
)
from ...services.everyday_interaction import (
    add_conversation_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    patch_conversation,
    promote_conversation_to_task,
)
from ...services.orchestrator_lookup import find_master_context_for_platform_task
from ...services.policy_engine import build_policy_explanation
from ...services.task_lifecycle import (
    approve_task,
    assign_task,
    local_bridge_result,
    create_task,
    get_timeline,
    get_execution_plan,
    mark_failed,
    register_local_bridge_agent,
    reject_task,
    retry_task,
    run_task,
)
from ...services.control_plane_agents import (
    create_control_plane_agent,
    delete_control_plane_agent,
    patch_control_plane_agent,
    start_agent_test_run,
)
from ...services.watchdog_metrics import (
    build_local_bridge_recent_callback_audit,
    build_metrics,
    build_watchdog_status,
    probe_local_bridge_detailed,
)
from ...services.observer import build_observer_summary
from ...services.runtime_supervision import run_runtime_supervision_cycle
from ...store.repositories import (
    accounts_repo,
    agents_repo,
    credentials_repo,
    file_artifacts_repo,
    local_bridge_repo,
    memory_repo,
    policies_repo,
    notification_channels_repo,
    notification_deliveries_repo,
    reports_repo,
    run_logs_repo,
    runs_repo,
    skills_repo,
    task_assignments_repo,
    task_events_repo,
    tasks_repo,
)
from ...services.notifications import upsert_channel
from ...services.api_profiles import (
    bind_agent,
    delete_profile,
    get_agent_binding,
    get_profile,
    list_profiles,
    test_profile_connectivity,
    upsert_profile,
)
from ...services.skills_executor import execute_skill
from ...services.credentials_service import create_credential
from ...services.reports_generate import generate_comparison_report
from ...skill_visibility import report_is_user_visible, skill_is_user_visible
from ...services.kanaloa_platform import (
    build_adapters_status_payload,
    build_agent_registry_entries,
    build_capabilities_payload,
)
from ...services.claude_adapter_dispatch import dispatch_claude
from ...services.kanaloa_actions import (
    cancel_agent_task,
    create_agent_task,
    dispatch_agent_task,
    list_agents as kanaloa_list_agents,
    list_recent_tasks,
    read_task_events,
    read_task_status,
)
from ...services.kanaloa_orchestrator import (
    cancel_master_task,
    get_master_task,
    list_recent_masters,
    orchestrator_begin_run,
    run_master_task_background,
)
from ...services.permission_gate import get_kanaloa_principal, require_scope
from ...services.idempotency import begin_idempotent_mutation, complete_idempotent_mutation
from ...version import PLATFORM_VERSION

router = APIRouter(tags=["platform"])

NOTE = "File-backed or Postgres persistence. User-created content is authoritative."


@router.get("/api/system/capabilities")
def api_system_capabilities():
    """Kanaloa orchestrator + platform facts (no secrets)."""
    return build_capabilities_payload()


@router.get("/api/adapters/status")
def api_adapters_status():
    """Live adapter health derived from Bridge probe + registry (no API keys)."""
    return build_adapters_status_payload()


@router.get("/api/agents/registry", response_model=ListResponse)
def api_agents_registry():
    return ListResponse(note=NOTE, items=build_agent_registry_entries())


@router.post("/api/adapters/claude-code/dispatch")
def api_claude_adapter_dispatch(body: ClaudeAdapterDispatchBody):
    return dispatch_claude(body)


@router.post("/api/kanaloa/actions/create-task")
def api_kanaloa_create_task(body: KanaloaCreateTaskBody):
    p = get_kanaloa_principal()
    return create_agent_task(
        p,
        agent_id=body.agent_id,
        instruction=body.instruction,
        mode=body.mode,
        workspace=body.workspace,
    )


@router.post("/api/kanaloa/actions/dispatch")
def api_kanaloa_dispatch_task(body: KanaloaDispatchBody):
    p = get_kanaloa_principal()
    return dispatch_agent_task(p, body.task_id)


@router.get("/api/kanaloa/actions/task/{task_id}")
def api_kanaloa_get_task(task_id: str):
    p = get_kanaloa_principal()
    return read_task_status(p, task_id)


@router.get("/api/kanaloa/actions/task/{task_id}/events")
def api_kanaloa_get_task_events(task_id: str):
    p = get_kanaloa_principal()
    return read_task_events(p, task_id)


@router.post("/api/kanaloa/actions/cancel")
def api_kanaloa_cancel_task(body: KanaloaCancelBody):
    p = get_kanaloa_principal()
    return cancel_agent_task(p, body.task_id)


@router.get("/api/kanaloa/actions/agents")
def api_kanaloa_list_agents():
    p = get_kanaloa_principal()
    return kanaloa_list_agents(p)


@router.get("/api/kanaloa/actions/recent-tasks")
def api_kanaloa_recent_tasks(limit: int = 8):
    p = get_kanaloa_principal()
    return list_recent_tasks(p, limit=limit)


@router.post("/api/kanaloa/orchestrator/run")
def api_kanaloa_orchestrator_run(body: KanaloaOrchestratorRunBody, background_tasks: BackgroundTasks):
    p = get_kanaloa_principal()
    if p.profile == "readonly":
        raise HTTPException(status_code=403, detail={"error": "readonly_profile"})
    require_scope(p, "tasks.create")
    master = orchestrator_begin_run(
        instruction=body.instruction,
        conversation_id=body.conversation_id,
        subtask_mode=body.subtask_mode,
    )
    background_tasks.add_task(run_master_task_background, master.master_task_id, body.subtask_mode)
    return {
        "ok": True,
        "master_task_id": master.master_task_id,
        "status": master.status,
        "message": "orchestrator run accepted",
    }


@router.get("/api/kanaloa/orchestrator/tasks")
def api_kanaloa_orchestrator_tasks_list(limit: int = 20):
    p = get_kanaloa_principal()
    require_scope(p, "tasks.read")
    lim = max(1, min(limit, 50))
    items = list_recent_masters(limit=lim)
    return {"ok": True, "items": [m.model_dump() for m in items]}


@router.get("/api/kanaloa/orchestrator/tasks/{master_task_id}")
def api_kanaloa_orchestrator_task_get(master_task_id: str):
    p = get_kanaloa_principal()
    require_scope(p, "tasks.read")
    m = get_master_task(master_task_id)
    if not m:
        raise HTTPException(status_code=404, detail="master_task_not_found")
    return {"ok": True, "master": m.model_dump()}


@router.get("/api/kanaloa/orchestrator/tasks/{master_task_id}/events")
def api_kanaloa_orchestrator_task_events(master_task_id: str):
    p = get_kanaloa_principal()
    require_scope(p, "tasks.read")
    require_scope(p, "audit.read")
    m = get_master_task(master_task_id)
    if not m:
        raise HTTPException(status_code=404, detail="master_task_not_found")
    return {"ok": True, "master_task_id": master_task_id, "events": m.events}


@router.post("/api/kanaloa/orchestrator/tasks/{master_task_id}/continue")
def api_kanaloa_orchestrator_task_continue(
    master_task_id: str,
    background_tasks: BackgroundTasks,
    body: KanaloaOrchestratorContinueBody | None = None,
):
    p = get_kanaloa_principal()
    if p.profile == "readonly":
        raise HTTPException(status_code=403, detail={"error": "readonly_profile"})
    require_scope(p, "tasks.create")
    if not get_master_task(master_task_id):
        raise HTTPException(status_code=404, detail="master_task_not_found")
    mode = body.subtask_mode if body else "execute"
    background_tasks.add_task(run_master_task_background, master_task_id, mode)
    return {
        "ok": True,
        "master_task_id": master_task_id,
        "status": "queued",
        "message": "orchestrator continue accepted",
    }


@router.post("/api/kanaloa/orchestrator/tasks/{master_task_id}/cancel")
def api_kanaloa_orchestrator_task_cancel(master_task_id: str):
    p = get_kanaloa_principal()
    if p.profile == "readonly":
        raise HTTPException(status_code=403, detail={"error": "readonly_profile"})
    require_scope(p, "tasks.cancel")
    return cancel_master_task(master_task_id, p).model_dump()


@router.get("/agents", response_model=ListResponse)
def agents_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = agents_repo.list()
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.get("/agents/{agent_id}")
def agents_get(agent_id: str):
    a = agents_repo.get(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="agent_not_found")
    bridge_state = local_bridge_repo.get(agent_id)
    api_profile = get_agent_binding(agent_id)
    return {"version": PLATFORM_VERSION, "note": NOTE, "data": a, "bridge_state": bridge_state, "api_profile": api_profile}


@router.post("/agents")
def agents_create(body: AgentCreateBody):
    a = create_control_plane_agent(body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": a}


@router.patch("/agents/{agent_id}")
def agents_patch(agent_id: str, body: AgentPatchBody):
    a = patch_control_plane_agent(agent_id, body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": a}


@router.delete("/agents/{agent_id}")
def agents_delete(agent_id: str):
    """物理删除 Agent（仅限外部 Agent，内置 Kanaloa 只能禁用）。"""
    result = delete_control_plane_agent(agent_id)
    return {"version": PLATFORM_VERSION, "ok": True, "data": result}


@router.post("/agents/{agent_id}/test-run")
def agents_test_run(agent_id: str):
    return {"version": PLATFORM_VERSION, **start_agent_test_run(agent_id)}


@router.get("/tasks", response_model=ListResponse)
def tasks_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = tasks_repo.list()
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.get("/conversations", response_model=ListResponse)
def conversations_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = list_conversations()
    window, meta = paginate(items, limit, offset)
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Everyday lightweight interaction history is persisted separately from long-term memory.",
        items=window,
        **meta,
    )


@router.post("/conversations")
def conversations_create(body: ConversationCreateBody):
    conversation = create_conversation(body)
    return {"version": PLATFORM_VERSION, "data": conversation}


@router.get("/conversations/{conversation_id}")
def conversations_get(conversation_id: str):
    return {"version": PLATFORM_VERSION, **get_conversation(conversation_id)}


@router.patch("/conversations/{conversation_id}")
def conversations_patch(conversation_id: str, body: ConversationPatchBody):
    conversation = patch_conversation(conversation_id, body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": conversation}


@router.delete("/conversations/{conversation_id}")
def conversations_delete(conversation_id: str, delete_memory: bool = False):
    """Physically delete a conversation with cascading messages.
    Set delete_memory=true to also remove memory items referencing this conversation.
    """
    result = delete_conversation(conversation_id, delete_memory=delete_memory)
    return {"version": PLATFORM_VERSION, "ok": True, "data": result}


@router.post("/conversations/{conversation_id}/messages")
def conversations_add_message(conversation_id: str, body: ConversationMessageBody):
    return {"version": PLATFORM_VERSION, **add_conversation_message(conversation_id, body)}


@router.post("/conversations/{conversation_id}/promote")
def conversations_promote(conversation_id: str, body: ConversationPromoteBody):
    return {"version": PLATFORM_VERSION, **promote_conversation_to_task(conversation_id, body)}


@router.post("/tasks")
def tasks_create(
    body: TaskCreateBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    cached = begin_idempotent_mutation("create_task", idempotency_key, payload)
    if cached is not None:
        return cached
    t = create_task(body)
    resp = {"version": PLATFORM_VERSION, "data": t}
    complete_idempotent_mutation(
        "create_task",
        idempotency_key,
        payload,
        {"version": PLATFORM_VERSION, "data": t.model_dump(mode="json")},
        task_id=t.task_id,
    )
    return resp


@router.get("/tasks/{task_id}")
def tasks_get(task_id: str):
    t = tasks_repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task_not_found")
    assignments = [a for a in task_assignments_repo.list() if a.task_id == task_id]
    assignments.sort(key=lambda x: x.assigned_at, reverse=True)
    orch = find_master_context_for_platform_task(task_id)
    return {"version": PLATFORM_VERSION, "note": NOTE, "data": t, "assignments": assignments, "orchestrator_context": orch}


@router.post("/tasks/{task_id}/assign")
def tasks_assign(task_id: str, body: TaskAssignBody):
    t = assign_task(task_id, body)
    return {"version": PLATFORM_VERSION, "data": t}


@router.post("/tasks/{task_id}/run")
def tasks_run(
    task_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    payload = {"task_id": task_id}
    cached = begin_idempotent_mutation("run_task", idempotency_key, payload)
    if cached is not None:
        return cached
    result = run_task(task_id)
    resp = {"version": PLATFORM_VERSION, **result}
    complete_idempotent_mutation("run_task", idempotency_key, payload, resp, task_id=task_id)
    return resp


@router.post("/tasks/{task_id}/retry")
def tasks_retry(task_id: str):
    t = retry_task(task_id)
    return {"version": PLATFORM_VERSION, "data": t}


@router.post("/tasks/{task_id}/fail")
def tasks_fail(task_id: str, body: TaskFailBody):
    t = mark_failed(task_id, body)
    return {"version": PLATFORM_VERSION, "data": t}


@router.get("/tasks/{task_id}/timeline")
def tasks_timeline(
    task_id: str,
    events_limit: int = Query(default=DEFAULT_TIMELINE_EVENTS_LIMIT, ge=1, le=MAX_TIMELINE_EVENTS_LIMIT),
    logs_limit: int = Query(default=DEFAULT_TIMELINE_LOGS_LIMIT, ge=1, le=MAX_TIMELINE_LOGS_LIMIT),
):
    return {"version": PLATFORM_VERSION, **get_timeline(task_id, events_limit=events_limit, logs_limit=logs_limit)}


@router.get("/tasks/{task_id}/plan")
def tasks_plan(task_id: str):
    return {"version": PLATFORM_VERSION, **get_execution_plan(task_id)}


@router.post("/tasks/{task_id}/approve")
def tasks_approve(task_id: str, body: TaskApproveBody):
    return {"version": PLATFORM_VERSION, **approve_task(task_id, body)}


@router.post("/tasks/{task_id}/reject")
def tasks_reject(task_id: str, body: TaskRejectBody):
    return {"version": PLATFORM_VERSION, **reject_task(task_id, body)}


@router.get("/runs")
def runs_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    runs = runs_repo.list()
    runs.sort(key=lambda x: x.finished_at or x.started_at or x.queued_at or "", reverse=True)
    window, meta = paginate(runs, limit, offset)
    return {"version": PLATFORM_VERSION, "note": NOTE, "items": window, **meta}


@router.get("/runs/{run_id}")
def runs_get(
    run_id: str,
    logs_limit: int = Query(default=DEFAULT_TIMELINE_LOGS_LIMIT, ge=1, le=MAX_TIMELINE_LOGS_LIMIT),
):
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    logs, logs_total = list_logs_for_run(run_id, tail=logs_limit)
    return {"version": PLATFORM_VERSION, "note": NOTE, "data": run, "logs": logs, "logs_total": logs_total}


@router.get("/skills", response_model=ListResponse)
def skills_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = [s for s in skills_repo.list() if skill_is_user_visible(s)]
    window, meta = paginate(items, limit, offset)
    return ListResponse(
        version=PLATFORM_VERSION,
        note=NOTE + " Internal-only skill markers in stored titles are filtered from this list.",
        items=window,
        **meta,
    )


@router.post("/skills/{skill_id}/execute")
def skills_execute(skill_id: str, body: SkillExecuteBody):
    res = execute_skill(skill_id, body)
    return {"version": PLATFORM_VERSION, "data": res.model_dump()}


@router.post("/skills/{skill_id}/publish")
def skills_publish(skill_id: str):
    """Promote a single-agent private Skill to a platform public Skill."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    updated = s.model_copy(update={"skill_scope": "platform", "owner_agent_id": None})
    skills_repo.upsert(updated)
    return {"version": PLATFORM_VERSION, "ok": True, "data": updated}


@router.patch("/skills/{skill_id}")
def skills_patch(skill_id: str, body: SkillPatchBody):
    """Partial update of a Skill. Currently supports toggling `enabled`."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    updates: dict = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.default_execution_policy is not None:
        updates["default_execution_policy"] = body.default_execution_policy
    if body.description is not None:
        updates["description"] = body.description
    if not updates:
        return {"version": PLATFORM_VERSION, "ok": True, "data": s, "note": "no_changes"}
    updated = s.model_copy(update=updates)
    skills_repo.upsert(updated)
    return {"version": PLATFORM_VERSION, "ok": True, "data": updated}


@router.delete("/skills/{skill_id}")
def skills_delete(skill_id: str):
    """Physically remove a Skill from the registry."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    skills_repo.delete(skill_id)
    return {"version": PLATFORM_VERSION, "ok": True, "deleted_id": skill_id}


@router.get("/accounts", response_model=ListResponse)
def accounts_list():
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=accounts_repo.list())


@router.get("/credentials", response_model=ListResponse)
def credentials_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = [c.model_copy(update={"secret_material": None}) for c in credentials_repo.list()]
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.post("/credentials")
def credentials_create(body: CredentialUpsertBody):
    res = create_credential(body)
    # never return secret material
    return {"version": PLATFORM_VERSION, "ok": True, **res}


@router.get("/memory", response_model=ListResponse)
def memory_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = memory_repo.list()
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.get("/memory/candidates", response_model=ListResponse)
def memory_candidates_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = [m for m in memory_repo.list() if m.status == "candidate"]
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Candidates filtered from memory store (status=candidate)",
        items=window,
        **meta,
    )


@router.post("/memory/candidates/{memory_id}/approve")
def approve_memory_candidate(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    if m.status != "candidate":
        raise HTTPException(status_code=400, detail="not_a_candidate")
    updated = m.model_copy(update={"status": "approved"})
    memory_repo.upsert(updated)
    return {"ok": True, "version": PLATFORM_VERSION, "note": "Optional API token in production; audit via GET /audit/export", "data": updated}


@router.post("/memory/candidates/{memory_id}/reject")
def reject_memory_candidate(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    if m.status != "candidate":
        raise HTTPException(status_code=400, detail="not_a_candidate")
    updated = m.model_copy(update={"status": "rejected"})
    memory_repo.upsert(updated)
    return {"ok": True, "version": PLATFORM_VERSION, "note": "Optional API token in production; audit via GET /audit/export", "data": updated}


@router.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    memory_repo.delete(memory_id)
    return {"ok": True, "version": PLATFORM_VERSION, "deleted_id": memory_id}


@router.get("/memory/export")
def memory_export(status: str | None = None, source_agent_id: str | None = None):
    """Export memory items as JSON. Optionally filter by status or source_agent_id."""
    items = memory_repo.list()
    if status:
        items = [m for m in items if m.status == status]
    if source_agent_id:
        items = [m for m in items if getattr(m, "source_agent_id", None) == source_agent_id]
    return {
        "version": PLATFORM_VERSION,
        "note": "Export is JSON only. CSV and pgvector export planned.",
        "count": len(items),
        "items": [m.model_dump() for m in items],
    }


# ---------------- File artifacts ----------------

@router.get("/files", response_model=ListResponse)
def files_list(
    task_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
):
    items = file_artifacts_repo.list()
    if task_id:
        items = [f for f in items if f.task_id == task_id]
    if conversation_id:
        items = [f for f in items if f.conversation_id == conversation_id]
    if agent_id:
        items = [f for f in items if f.agent_id == agent_id]
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=items)


@router.post("/files")
def files_create(body: FileArtifactCreateBody):
    from datetime import datetime, timezone
    import uuid

    artifact = FileArtifact(
        file_id=f"file_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        **body.model_dump(),
    )
    file_artifacts_repo.upsert(artifact)
    return {"version": PLATFORM_VERSION, "data": artifact}


@router.delete("/files/{file_id}")
def files_delete(file_id: str):
    existing = file_artifacts_repo.get(file_id)
    if not existing:
        raise HTTPException(status_code=404, detail="file_not_found")
    file_artifacts_repo.delete(file_id)
    return {"ok": True, "version": PLATFORM_VERSION, "deleted_id": file_id}


@router.get("/watchdog")
def watchdog_get():
    st = build_watchdog_status()
    return {"version": PLATFORM_VERSION, "note": "Watchdog rules for self-hosted ops; not production SLOs", "data": st}


@router.get("/escalations", response_model=ListResponse)
def escalations_list(status: str | None = None):
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Escalations reuse latest watchdog issue state; human actions append audit events instead of creating a separate module.",
        items=list_escalations(status=status),
    )


@router.post("/escalations/{event_id}/acknowledge")
def escalations_acknowledge(event_id: str, body: EscalationActionBody | None = None):
    event = update_escalation(event_id, "processing", body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": event}


@router.post("/escalations/{event_id}/resolve")
def escalations_resolve(event_id: str, body: EscalationActionBody | None = None):
    event = update_escalation(event_id, "resolved", body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": event}


@router.get("/metrics")
def metrics_get():
    return {"version": PLATFORM_VERSION, **build_metrics()}


@router.get("/observer")
def observer_get(limit: int = 12):
    return {
        "version": PLATFORM_VERSION,
        "note": "Observer is read-only. It summarizes persisted run/task/recovery packets without intervening in execution.",
        "data": build_observer_summary(limit=max(4, min(limit, 30))),
    }


@router.get("/advisor")
def advisor_get(limit: int = 6):
    return {
        "version": PLATFORM_VERSION,
        "note": "Advisor is read-mostly in Phase A. It explains persisted issues and policy friction without executing actions.",
        "data": build_advisor_summary(limit=max(1, min(limit, 12))),
    }


@router.get("/advisor/suggestions", response_model=ListResponse)
def advisor_suggestions_list(
    status: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    suggestion_type: str | None = None,
):
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Advisor suggestions are persisted and auditable, but accept/dismiss only records operator intent.",
        items=list_advisor_suggestions(
            status=status,
            target_type=target_type,
            target_id=target_id,
            suggestion_type=suggestion_type,
        ),
    )


@router.get("/advisor/tasks/{task_id}", response_model=ListResponse)
def advisor_task_suggestions(task_id: str):
    task = tasks_repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Task-scoped advisor notes are read-only recommendations based on persisted events and runs.",
        items=build_task_advice(task_id),
    )


@router.post("/advisor/suggestions/{suggestion_id}/accept")
def advisor_suggestions_accept(suggestion_id: str):
    suggestion = accept_advisor_suggestion(suggestion_id)
    return {"version": PLATFORM_VERSION, "ok": True, "data": suggestion}


@router.post("/advisor/suggestions/{suggestion_id}/dismiss")
def advisor_suggestions_dismiss(suggestion_id: str):
    suggestion = dismiss_advisor_suggestion(suggestion_id)
    return {"version": PLATFORM_VERSION, "ok": True, "data": suggestion}


@router.post("/runtime/supervision/run")
def runtime_supervision_run():
    return {
        "version": PLATFORM_VERSION,
        "note": "Explicit probe endpoint for runtime supervision. GET endpoints remain read-only.",
        "data": run_runtime_supervision_cycle(),
    }


# ── P3 Governor ───────────────────────────────────────────────────────────────

@router.get("/governor")
def governor_summary_get():
    return {
        "version": PLATFORM_VERSION,
        "note": (
            "Governor is P3 controlled execution. "
            "It evaluates AdvisorSuggestions through safety gates and produces auditable decisions. "
            "Execution only happens inside the defined allowlist."
        ),
        "data": get_governor_summary(),
    }


@router.get("/governor/decisions", response_model=ListResponse)
def governor_decisions_list(status: str | None = None):
    return ListResponse(
        version=PLATFORM_VERSION,
        note="Governor decisions are fully auditable. accept/deny/execute only records operator intent + receipts.",
        items=list_decisions(status=status),
    )


@router.get("/governor/decisions/{decision_id}")
def governor_decision_get(decision_id: str):
    decision = get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="governor_decision_not_found")
    return {"version": PLATFORM_VERSION, "data": decision}


@router.post("/governor/evaluate")
def governor_evaluate(body: GovernorEvaluateBody):
    """
    Evaluate an AdvisorSuggestion through all Governor gates.
    Returns a GovernorDecision (auto_execute | require_confirmation | deny).
    If decision=auto_execute, the action is executed immediately.
    """
    action, decision = build_and_evaluate(
        suggestion_id=body.suggestion_id,
        action_type=body.action_type,
        target_id=body.target_id,
        target_type=body.target_type,
        parameters=body.parameters,
    )
    return {"version": PLATFORM_VERSION, "ok": True, "action": action, "decision": decision}


@router.post("/governor/decisions/{decision_id}/confirm")
def governor_decision_confirm(decision_id: str):
    """Human confirms a pending require_confirmation decision. Executes the action."""
    receipt = confirm_decision(decision_id, confirmed_by="human")
    return {"version": PLATFORM_VERSION, "ok": True, "receipt": receipt}


@router.get("/policies", response_model=ListResponse)
def policies_list():
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=policies_repo.list())


@router.get("/policies/explain")
def policies_explain(scope: str = "global", target_id: str | None = None):
    return {
        "version": PLATFORM_VERSION,
        "note": "Effective policy explanation is read-only and follows current runtime precedence rules.",
        "data": build_policy_explanation(scope, target_id),
    }


@router.post("/policies")
def policies_upsert(body: ExecutionPolicyUpsertBody):
    # Opt-in enforcement: is_draft=false means policy_engine will apply it.
    pol = policies_repo.model.model_validate(body.model_dump())
    policies_repo.upsert(pol)
    return {"version": PLATFORM_VERSION, "ok": True, "data": pol}


@router.get("/notifications/channels", response_model=ListResponse)
def notification_channels_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    window, meta = paginate(notification_channels_repo.list(), limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.post("/notifications/channels")
def notification_channels_upsert(body: NotificationChannelUpsertBody):
    ch = upsert_channel(body.model_dump())
    return {"version": PLATFORM_VERSION, "ok": True, "data": ch}


@router.get("/notifications/deliveries", response_model=ListResponse)
def notification_deliveries_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = notification_deliveries_repo.list()
    items.sort(key=lambda x: x.created_at, reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.get("/api-profiles", response_model=ListResponse)
def api_profiles_list():
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=list_profiles())


@router.post("/api-profiles")
def api_profiles_upsert(body: AgentApiProfileUpsertBody):
    p = upsert_profile(body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": p}


@router.get("/api-profiles/{profile_id}")
def api_profiles_get(profile_id: str):
    return {"version": PLATFORM_VERSION, "data": get_profile(profile_id)}


@router.delete("/api-profiles/{profile_id}")
def api_profiles_delete(profile_id: str):
    return {"version": PLATFORM_VERSION, "ok": True, "data": delete_profile(profile_id)}


@router.post("/api-profiles/{profile_id}/test")
def api_profiles_test(profile_id: str):
    return {"version": PLATFORM_VERSION, "data": test_profile_connectivity(profile_id)}


@router.post("/agents/{agent_id}/api-profile")
def agent_bind_api_profile(agent_id: str, body: AgentApiBindingBody):
    b = bind_agent(agent_id, body.profile_id)
    return {"version": PLATFORM_VERSION, "ok": True, "data": b}


@router.get("/local-bridge")
def local_bridge_status():
    m = build_metrics()
    lb = m.get("local_bridge", {})
    bridge_agents = local_bridge_repo.list()
    bridge_agents.sort(key=lambda x: x.last_seen_at, reverse=True)
    probe = probe_local_bridge_detailed()
    bs = probe.get("bridge_status") if isinstance(probe.get("bridge_status"), dict) else {}
    le = bs.get("last_execute") if isinstance(bs.get("last_execute"), dict) else {}
    return {
        "version": PLATFORM_VERSION,
        "note": "API probes Local Bridge /health and returns persisted bridge agent state. Use POST /local-bridge/probe for a fresh check.",
        "data": {
            "url": lb.get("url"),
            "reachable": lb.get("reachable"),
            "registered_agents": bridge_agents,
            "last_seen_at": lb.get("last_seen_at"),
            "metrics_bridge_registered_total": lb.get("registered_agents"),
            "recent_callback_audit": build_local_bridge_recent_callback_audit(),
            "docs": "See docs/EXTERNAL_AGENT_INTEGRATION.md and apps/local-bridge/README.md",
            "bridge_runtime": {
                "reachable": probe.get("reachable"),
                "last_execute_at": le.get("at"),
                "last_execute_error": le.get("last_error"),
                "handoff_dir": bs.get("handoff_dir"),
                "api_public_url": probe.get("api_public_url"),
                "probed_at": probe.get("probed_at"),
            },
        },
    }


@router.post("/local-bridge/probe")
def local_bridge_probe():
    return {"version": PLATFORM_VERSION, "data": probe_local_bridge_detailed()}


@router.post("/local-bridge/register")
def local_bridge_register(body: LocalBridgeRegisterBody):
    state = register_local_bridge_agent(body)
    return {"version": PLATFORM_VERSION, "ok": True, "data": state}


@router.post("/local-bridge/result")
def local_bridge_result_route(body: LocalBridgeResultBody):
    return {"version": PLATFORM_VERSION, **local_bridge_result(body)}


@router.get("/audit/export")
def audit_export(
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """Export audit.* task events for compliance review."""
    events = [e for e in task_events_repo.list() if (e.type or "").startswith("audit.")]
    events.sort(key=lambda e: e.created_at or "", reverse=True)
    window, meta = paginate(events, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note=NOTE, items=window, **meta)


@router.get("/reports", response_model=ListResponse)
def reports_list(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = [r for r in reports_repo.list() if report_is_user_visible(r)]
    items.sort(key=lambda x: x.created_at or "", reverse=True)
    window, meta = paginate(items, limit, offset)
    return ListResponse(
        version=PLATFORM_VERSION,
        note=NOTE + " Draft reports and legacy internal title markers are omitted from this list.",
        items=window,
        **meta,
    )


@router.post("/reports/generate")
def reports_generate():
    r = generate_comparison_report()
    return {"version": PLATFORM_VERSION, "ok": True, "data": r}


@router.get("/reports/{report_id}")
def reports_get(report_id: str):
    r = reports_repo.get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report_not_found")
    return {"version": PLATFORM_VERSION, "note": NOTE, "data": r}

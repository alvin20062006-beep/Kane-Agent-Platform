from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...models import (
    ConversationCreateBody,
    ConversationMessageBody,
    ConversationPatchBody,
    ConversationPromoteBody,
    ExecutionPolicyUpsertBody,
    AgentApiBindingBody,
    AgentApiProfileUpsertBody,
    AgentCreateBody,
    AgentPatchBody,
    FileArtifact,
    FileArtifactCreateBody,
    NotificationChannelUpsertBody,
    ListResponse,
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
from ...services.everyday_interaction import (
    add_conversation_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    patch_conversation,
    promote_conversation_to_task,
)
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
from ...services.watchdog_metrics import build_metrics, build_watchdog_status, probe_local_bridge_detailed
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
    tasks_repo,
)
from ...services.notifications import upsert_channel
from ...services.api_profiles import bind_agent, get_agent_binding, get_profile, list_profiles, upsert_profile
from ...services.skills_executor import execute_skill
from ...services.credentials_service import create_credential
from ...services.reports_generate import generate_comparison_report
from ...skill_visibility import report_is_user_visible, skill_is_user_visible

router = APIRouter(tags=["platform"])

NOTE = "File-backed or Postgres persistence (Public Free Beta). User-created content is authoritative."


@router.get("/agents", response_model=ListResponse)
def agents_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=agents_repo.list())


@router.get("/agents/{agent_id}")
def agents_get(agent_id: str):
    a = agents_repo.get(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="agent_not_found")
    bridge_state = local_bridge_repo.get(agent_id)
    api_profile = get_agent_binding(agent_id)
    return {"beta": True, "note": NOTE, "data": a, "bridge_state": bridge_state, "api_profile": api_profile}


@router.post("/agents")
def agents_create(body: AgentCreateBody):
    a = create_control_plane_agent(body)
    return {"beta": True, "ok": True, "data": a}


@router.patch("/agents/{agent_id}")
def agents_patch(agent_id: str, body: AgentPatchBody):
    a = patch_control_plane_agent(agent_id, body)
    return {"beta": True, "ok": True, "data": a}


@router.delete("/agents/{agent_id}")
def agents_delete(agent_id: str):
    """物理删除 Agent（仅限外部 Agent，内置 Kanaloa 只能禁用）。"""
    result = delete_control_plane_agent(agent_id)
    return {"beta": True, "ok": True, "data": result}


@router.post("/agents/{agent_id}/test-run")
def agents_test_run(agent_id: str):
    return {"beta": True, **start_agent_test_run(agent_id)}


@router.get("/tasks", response_model=ListResponse)
def tasks_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=tasks_repo.list())


@router.get("/conversations", response_model=ListResponse)
def conversations_list():
    return ListResponse(
        is_mock=False,
        beta=True,
        note="Everyday lightweight interaction history is persisted separately from long-term memory.",
        items=list_conversations(),
    )


@router.post("/conversations")
def conversations_create(body: ConversationCreateBody):
    conversation = create_conversation(body)
    return {"beta": True, "data": conversation}


@router.get("/conversations/{conversation_id}")
def conversations_get(conversation_id: str):
    return {"beta": True, **get_conversation(conversation_id)}


@router.patch("/conversations/{conversation_id}")
def conversations_patch(conversation_id: str, body: ConversationPatchBody):
    conversation = patch_conversation(conversation_id, body)
    return {"beta": True, "ok": True, "data": conversation}


@router.delete("/conversations/{conversation_id}")
def conversations_delete(conversation_id: str, delete_memory: bool = False):
    """Physically delete a conversation with cascading messages.
    Set delete_memory=true to also remove memory items referencing this conversation.
    """
    result = delete_conversation(conversation_id, delete_memory=delete_memory)
    return {"beta": True, "ok": True, "data": result}


@router.post("/conversations/{conversation_id}/messages")
def conversations_add_message(conversation_id: str, body: ConversationMessageBody):
    return {"beta": True, **add_conversation_message(conversation_id, body)}


@router.post("/conversations/{conversation_id}/promote")
def conversations_promote(conversation_id: str, body: ConversationPromoteBody):
    return {"beta": True, **promote_conversation_to_task(conversation_id, body)}


@router.post("/tasks")
def tasks_create(body: TaskCreateBody):
    t = create_task(body)
    return {"beta": True, "data": t}


@router.get("/tasks/{task_id}")
def tasks_get(task_id: str):
    t = tasks_repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task_not_found")
    assignments = [a for a in task_assignments_repo.list() if a.task_id == task_id]
    assignments.sort(key=lambda x: x.assigned_at, reverse=True)
    return {"beta": True, "note": NOTE, "data": t, "assignments": assignments}


@router.post("/tasks/{task_id}/assign")
def tasks_assign(task_id: str, body: TaskAssignBody):
    t = assign_task(task_id, body)
    return {"beta": True, "data": t}


@router.post("/tasks/{task_id}/run")
def tasks_run(task_id: str):
    return {"beta": True, **run_task(task_id)}


@router.post("/tasks/{task_id}/retry")
def tasks_retry(task_id: str):
    t = retry_task(task_id)
    return {"beta": True, "data": t}


@router.post("/tasks/{task_id}/fail")
def tasks_fail(task_id: str, body: TaskFailBody):
    t = mark_failed(task_id, body)
    return {"beta": True, "data": t}


@router.get("/tasks/{task_id}/timeline")
def tasks_timeline(task_id: str):
    return {"beta": True, **get_timeline(task_id)}


@router.get("/tasks/{task_id}/plan")
def tasks_plan(task_id: str):
    return {"beta": True, **get_execution_plan(task_id)}


@router.post("/tasks/{task_id}/approve")
def tasks_approve(task_id: str, body: TaskApproveBody):
    return {"beta": True, **approve_task(task_id, body)}


@router.post("/tasks/{task_id}/reject")
def tasks_reject(task_id: str, body: TaskRejectBody):
    return {"beta": True, **reject_task(task_id, body)}


@router.get("/runs")
def runs_list():
    runs = runs_repo.list()
    runs.sort(key=lambda x: x.started_at, reverse=True)
    return {"beta": True, "note": NOTE, "items": runs}


@router.get("/runs/{run_id}")
def runs_get(run_id: str):
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    logs = [l for l in run_logs_repo.list() if l.run_id == run_id]
    logs.sort(key=lambda x: x.seq)
    return {"beta": True, "note": NOTE, "data": run, "logs": logs}


@router.get("/skills", response_model=ListResponse)
def skills_list():
    items = [s for s in skills_repo.list() if skill_is_user_visible(s)]
    return ListResponse(
        is_mock=False,
        beta=True,
        note=NOTE + " Skills marked [MOCK] in stored data are omitted from this list.",
        items=items,
    )


@router.post("/skills/{skill_id}/execute")
def skills_execute(skill_id: str, body: SkillExecuteBody):
    res = execute_skill(skill_id, body)
    return {"beta": True, "data": res.model_dump()}


@router.post("/skills/{skill_id}/publish")
def skills_publish(skill_id: str):
    """Promote a single-agent private Skill to a platform public Skill."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    updated = s.model_copy(update={"skill_scope": "platform", "owner_agent_id": None})
    skills_repo.upsert(updated)
    return {"beta": True, "ok": True, "data": updated}


@router.patch("/skills/{skill_id}")
def skills_patch(skill_id: str, body: SkillPatchBody):
    """Partial update of a Skill. Currently supports toggling `enabled`."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    updates: dict = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if not updates:
        return {"beta": True, "ok": True, "data": s, "note": "no_changes"}
    updated = s.model_copy(update=updates)
    skills_repo.upsert(updated)
    return {"beta": True, "ok": True, "data": updated}


@router.delete("/skills/{skill_id}")
def skills_delete(skill_id: str):
    """Physically remove a Skill from the registry."""
    s = skills_repo.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail="skill_not_found")
    skills_repo.delete(skill_id)
    return {"beta": True, "ok": True, "deleted_id": skill_id}


@router.get("/accounts", response_model=ListResponse)
def accounts_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=accounts_repo.list())


@router.get("/credentials", response_model=ListResponse)
def credentials_list():
    items = [c.model_copy(update={"secret_material": None}) for c in credentials_repo.list()]
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=items)


@router.post("/credentials")
def credentials_create(body: CredentialUpsertBody):
    res = create_credential(body)
    # never return secret material
    return {"beta": True, "ok": True, **res}


@router.get("/memory", response_model=ListResponse)
def memory_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=memory_repo.list())


@router.get("/memory/candidates", response_model=ListResponse)
def memory_candidates_list():
    items = [m for m in memory_repo.list() if m.status == "candidate"]
    return ListResponse(
        is_mock=False,
        beta=True,
        note="Candidates filtered from memory store (status=candidate)",
        items=items,
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
    return {"ok": True, "beta": True, "note": "Beta: no auth/audit yet", "data": updated}


@router.post("/memory/candidates/{memory_id}/reject")
def reject_memory_candidate(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    if m.status != "candidate":
        raise HTTPException(status_code=400, detail="not_a_candidate")
    updated = m.model_copy(update={"status": "rejected"})
    memory_repo.upsert(updated)
    return {"ok": True, "beta": True, "note": "Beta: no auth/audit yet", "data": updated}


@router.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    memory_repo.delete(memory_id)
    return {"ok": True, "beta": True, "deleted_id": memory_id}


@router.get("/memory/export")
def memory_export(status: str | None = None, source_agent_id: str | None = None):
    """Export memory items as JSON. Optionally filter by status or source_agent_id."""
    items = memory_repo.list()
    if status:
        items = [m for m in items if m.status == status]
    if source_agent_id:
        items = [m for m in items if getattr(m, "source_agent_id", None) == source_agent_id]
    return {
        "beta": True,
        "note": "Export is JSON only in Beta. CSV and pgvector export planned.",
        "count": len(items),
        "items": [m.model_dump() for m in items],
    }


# ---------------- File artifacts (Beta) ----------------

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
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=items)


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
    return {"beta": True, "data": artifact}


@router.delete("/files/{file_id}")
def files_delete(file_id: str):
    existing = file_artifacts_repo.get(file_id)
    if not existing:
        raise HTTPException(status_code=404, detail="file_not_found")
    file_artifacts_repo.delete(file_id)
    return {"ok": True, "beta": True, "deleted_id": file_id}


@router.get("/watchdog")
def watchdog_get():
    st = build_watchdog_status()
    return {"beta": True, "note": "Beta watchdog rules; not production SLOs", "data": st}


@router.get("/metrics")
def metrics_get():
    return {"beta": True, **build_metrics()}


@router.get("/policies", response_model=ListResponse)
def policies_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=policies_repo.list())


@router.post("/policies")
def policies_upsert(body: ExecutionPolicyUpsertBody):
    # Opt-in enforcement: is_mock=false means policy_engine will apply it.
    pol = policies_repo.model.model_validate(body.model_dump())
    policies_repo.upsert(pol)
    return {"beta": True, "ok": True, "data": pol}


@router.get("/notifications/channels", response_model=ListResponse)
def notification_channels_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=notification_channels_repo.list())


@router.post("/notifications/channels")
def notification_channels_upsert(body: NotificationChannelUpsertBody):
    ch = upsert_channel(body.model_dump())
    return {"beta": True, "ok": True, "data": ch}


@router.get("/notifications/deliveries", response_model=ListResponse)
def notification_deliveries_list():
    items = notification_deliveries_repo.list()
    items.sort(key=lambda x: x.created_at, reverse=True)
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=items[:200])


@router.get("/api-profiles", response_model=ListResponse)
def api_profiles_list():
    return ListResponse(is_mock=False, beta=True, note=NOTE, items=list_profiles())


@router.post("/api-profiles")
def api_profiles_upsert(body: AgentApiProfileUpsertBody):
    p = upsert_profile(body)
    return {"beta": True, "ok": True, "data": p}


@router.get("/api-profiles/{profile_id}")
def api_profiles_get(profile_id: str):
    return {"beta": True, "data": get_profile(profile_id)}


@router.post("/agents/{agent_id}/api-profile")
def agent_bind_api_profile(agent_id: str, body: AgentApiBindingBody):
    b = bind_agent(agent_id, body.profile_id)
    return {"beta": True, "ok": True, "data": b}


@router.get("/local-bridge")
def local_bridge_status():
    m = build_metrics()
    lb = m.get("local_bridge", {})
    bridge_agents = local_bridge_repo.list()
    bridge_agents.sort(key=lambda x: x.last_seen_at, reverse=True)
    return {
        "beta": True,
        "note": "Beta: API probes Local Bridge /health and returns persisted bridge agent state. Use POST /local-bridge/probe for a fresh check.",
        "data": {
            "url": lb.get("url"),
            "reachable": lb.get("reachable"),
            "registered_agents": bridge_agents,
            "last_seen_at": lb.get("last_seen_at"),
            "metrics_bridge_registered_total": lb.get("registered_agents"),
            "docs": "See docs/EXTERNAL_AGENT_INTEGRATION.md and apps/local-bridge/README.md",
        },
    }


@router.post("/local-bridge/probe")
def local_bridge_probe():
    return {"beta": True, "data": probe_local_bridge_detailed()}


@router.post("/local-bridge/register")
def local_bridge_register(body: LocalBridgeRegisterBody):
    state = register_local_bridge_agent(body)
    return {"beta": True, "ok": True, "data": state}


@router.post("/local-bridge/result")
def local_bridge_result_route(body: LocalBridgeResultBody):
    return {"beta": True, **local_bridge_result(body)}


@router.get("/reports", response_model=ListResponse)
def reports_list():
    items = [r for r in reports_repo.list() if report_is_user_visible(r)]
    return ListResponse(
        is_mock=False,
        beta=True,
        note=NOTE + " Mock reports (is_mock or [MOCK] title) are omitted from this list.",
        items=items,
    )


@router.post("/reports/generate")
def reports_generate():
    r = generate_comparison_report()
    return {"beta": True, "ok": True, "data": r}


@router.get("/reports/{report_id}")
def reports_get(report_id: str):
    r = reports_repo.get(report_id)
    if not r:
        raise HTTPException(status_code=404, detail="report_not_found")
    return {"beta": True, "note": NOTE, "data": r}

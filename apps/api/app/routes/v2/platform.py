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
from ...store.run_step_queries import list_steps_for_run

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
    MemoryEvidenceSearchBody,
    MemoryCompilerCandidateCommitBody,
    MemoryCompilerRunCreateBody,
    MemoryEventAppendBody,
    MemoryExactRetrievalBody,
    MemoryPurgeBody,
    MemoryRuntimeContextBody,
    MemoryRewriteBody,
    NotificationChannelUpsertBody,
    ReferenceAggregationCreateBody,
    ReferenceCandidateCreateBody,
    RepairAttemptCreateBody,
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
    VerifierResultCreateBody,
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
    memory_index_repo,
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
from ...services.memory_ledger import (
    append_memory_event,
    rebuild_active_snapshot,
    record_memory_item_event,
    user_delete_memory,
    user_purge_memory,
    user_rewrite_memory,
)
from ...store.memory_event_queries import list_memory_events
from ...services.memory_retrieval import (
    build_runtime_memory_context,
    exact_retrieve,
    native_evidence_search,
)
from ...services.memory_compiler import (
    commit_memory_compiler_candidate,
    get_memory_compiler_candidate,
    get_memory_compiler_run,
    list_memory_compiler_candidates,
    list_memory_compiler_runs,
    run_memory_compiler,
)
from ...services.reference_layer import (
    create_aggregator_decision,
    create_reference_candidate,
    get_aggregator_decision,
    get_reference_candidate,
    list_aggregator_decisions,
    list_reference_candidates,
)
from ...services.verifier_interface import (
    create_verifier_result,
    get_verifier_result,
    list_verifier_results,
)
from ...services.repair_loop import (
    create_repair_attempt,
    get_repair_attempt,
    list_repair_attempts,
)
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


@router.get("/runs/{run_id}/steps")
def runs_steps(run_id: str):
    run = runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    steps, steps_total = list_steps_for_run(run_id)
    return {"version": PLATFORM_VERSION, "note": NOTE, "items": steps, "total": steps_total}


@router.post("/runs/{run_id}/verifier-results")
def runs_verifier_result_create(run_id: str, body: VerifierResultCreateBody):
    result = create_verifier_result(
        run_id=run_id,
        run_step_id=body.run_step_id,
        verifier_type=body.verifier_type,
        status=body.status,
        passed=body.passed,
        findings=body.findings,
        command_key=body.command_key,
        check_key=body.check_key,
        output_summary=body.output_summary,
        error_summary=body.error_summary,
        evidence_refs=body.evidence_refs,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": result}


@router.get("/runs/{run_id}/verifier-results", response_model=ListResponse)
def runs_verifier_results_list(
    run_id: str,
    run_step_id: str | None = None,
    verifier_type: str | None = None,
    status: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    if not runs_repo.get(run_id):
        raise HTTPException(status_code=404, detail="run_not_found")
    items = list_verifier_results(
        run_id=run_id,
        run_step_id=run_step_id,
        verifier_type=verifier_type,
        status=status,
    )
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Verifier results are recorded interface outputs only.", items=window, **meta)


@router.get("/verifier-results/{result_id}")
def verifier_result_get(result_id: str):
    result = get_verifier_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="verifier_result_not_found")
    return {"version": PLATFORM_VERSION, "data": result}


@router.post("/runs/{run_id}/repair-attempts")
def runs_repair_attempt_create(run_id: str, body: RepairAttemptCreateBody):
    attempt = create_repair_attempt(
        run_id=run_id,
        run_step_id=body.run_step_id,
        verifier_result_id=body.verifier_result_id,
        failure_id=body.failure_id,
        failure_ref=body.failure_ref,
        failure_type=body.failure_type,
        attempt_kind=body.attempt_kind,
        status=body.status,
        repair_action=body.repair_action,
        action_key=body.action_key,
        repair_key=body.repair_key,
        needs_user_confirmation=body.needs_user_confirmation,
        high_risk=body.high_risk,
        user_confirmed=body.user_confirmed,
        evidence_refs=body.evidence_refs,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": attempt}


@router.get("/runs/{run_id}/repair-attempts", response_model=ListResponse)
def runs_repair_attempts_list(
    run_id: str,
    run_step_id: str | None = None,
    verifier_result_id: str | None = None,
    status: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    if not runs_repo.get(run_id):
        raise HTTPException(status_code=404, detail="run_not_found")
    items = list_repair_attempts(
        run_id=run_id,
        run_step_id=run_step_id,
        verifier_result_id=verifier_result_id,
        status=status,
    )
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Retry and repair attempts are execution evidence only.", items=window, **meta)


@router.get("/repair-attempts/{repair_attempt_id}")
def repair_attempt_get(repair_attempt_id: str):
    attempt = get_repair_attempt(repair_attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="repair_attempt_not_found")
    return {"version": PLATFORM_VERSION, "data": attempt}


@router.post("/runs/{run_id}/reference-candidates")
def runs_reference_candidate_create(run_id: str, body: ReferenceCandidateCreateBody):
    candidate = create_reference_candidate(
        run_id=run_id,
        run_step_id=body.run_step_id,
        agent_role=body.agent_role,
        summary=body.summary,
        risks=body.risks,
        recommended_plan=body.recommended_plan,
        files_to_touch=body.files_to_touch,
        confidence=body.confidence,
        evidence_refs=body.evidence_refs,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": candidate}


@router.get("/runs/{run_id}/reference-candidates", response_model=ListResponse)
def runs_reference_candidates_list(
    run_id: str,
    run_step_id: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = list_reference_candidates(run_id=run_id, run_step_id=run_step_id)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Reference candidates are advisory only.", items=window, **meta)


@router.get("/reference-candidates/{candidate_id}")
def reference_candidate_get(candidate_id: str):
    candidate = get_reference_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="reference_candidate_not_found")
    return {"version": PLATFORM_VERSION, "data": candidate}


@router.post("/runs/{run_id}/reference-aggregations")
def runs_reference_aggregation_create(run_id: str, body: ReferenceAggregationCreateBody):
    decision = create_aggregator_decision(
        run_id=run_id,
        run_step_id=body.run_step_id,
        candidate_ids=body.candidate_ids,
        requires_user_confirmation=body.requires_user_confirmation,
        known_gaps=body.known_gaps,
        verifier_requirements=body.verifier_requirements,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": decision}


@router.get("/runs/{run_id}/reference-aggregations", response_model=ListResponse)
def runs_reference_aggregations_list(
    run_id: str,
    run_step_id: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = list_aggregator_decisions(run_id=run_id, run_step_id=run_step_id)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Reference aggregation decisions for run timeline.", items=window, **meta)


@router.get("/reference-aggregations/{aggregation_id}")
def reference_aggregation_get(aggregation_id: str):
    decision = get_aggregator_decision(aggregation_id)
    if not decision:
        raise HTTPException(status_code=404, detail="reference_aggregation_not_found")
    return {"version": PLATFORM_VERSION, "data": decision}


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


@router.post("/memory/events")
def memory_events_append(body: MemoryEventAppendBody):
    event = append_memory_event(
        event_type=body.event_type,
        memory_id=body.memory_id,
        subject_key=body.subject_key,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        source_type=body.source_type,
        source_id=body.source_id,
        run_id=body.run_id,
        run_step_id=body.run_step_id,
        task_id=body.task_id,
        conversation_id=body.conversation_id,
        skill_id=body.skill_id,
        decision_id=body.decision_id,
        failure_id=body.failure_id,
        content_json=body.content_json,
        value_json=body.value_json,
        evidence_refs=body.evidence_refs,
        confidence=body.confidence,
        policy_result=body.policy_result,
        supersedes_event_id=body.supersedes_event_id,
        invalidates_event_id=body.invalidates_event_id,
        created_by=body.created_by,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": event}


@router.get("/memory/events", response_model=ListResponse)
def memory_events_list(
    memory_id: str | None = None,
    event_type: str | None = None,
    subject_key: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    events = list_memory_events(memory_id=memory_id, event_type=event_type, subject_key=subject_key)
    window, meta = paginate(events, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Append-only AI memory ledger events.", items=window, **meta)


@router.get("/memory/index", response_model=ListResponse)
def memory_index_list(status: str | None = None):
    items = memory_index_repo.list()
    if status:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return ListResponse(version=PLATFORM_VERSION, note="Current memory projection; not a retrieval framework.", items=items)


@router.get("/memory/snapshot")
def memory_snapshot_get():
    snapshot = rebuild_active_snapshot()
    return {
        "version": PLATFORM_VERSION,
        "note": "Active Snapshot is prompt-eligible summary data; the ledger is not injected directly.",
        "data": snapshot,
    }


@router.post("/memory/compiler/runs")
def memory_compiler_run_create(body: MemoryCompilerRunCreateBody):
    compiler_run, candidates = run_memory_compiler(
        run_id=body.run_id,
        task_id=body.task_id,
        dry_run=body.dry_run,
        max_candidates=body.max_candidates,
        metadata=body.metadata,
    )
    return {
        "ok": True,
        "version": PLATFORM_VERSION,
        "note": "Compiler runs are dry-run only; commit a candidate explicitly to append MemoryEvent.",
        "data": compiler_run,
        "candidates": candidates,
    }


@router.get("/memory/compiler/runs", response_model=ListResponse)
def memory_compiler_runs_list(
    run_id: str | None = None,
    task_id: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = list_memory_compiler_runs(run_id=run_id, task_id=task_id)
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Background Memory Compiler dry-run records.", items=window, **meta)


@router.get("/memory/compiler/runs/{compiler_run_id}")
def memory_compiler_run_get(compiler_run_id: str):
    compiler_run = get_memory_compiler_run(compiler_run_id)
    if not compiler_run:
        raise HTTPException(status_code=404, detail="memory_compiler_run_not_found")
    candidates = list_memory_compiler_candidates(compiler_run_id=compiler_run_id)
    return {"version": PLATFORM_VERSION, "data": compiler_run, "candidates": candidates}


@router.get("/memory/compiler/candidates", response_model=ListResponse)
def memory_compiler_candidates_list(
    compiler_run_id: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    candidate_type: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    items = list_memory_compiler_candidates(
        compiler_run_id=compiler_run_id,
        run_id=run_id,
        task_id=task_id,
        status=status,
        candidate_type=candidate_type,
    )
    window, meta = paginate(items, limit, offset)
    return ListResponse(version=PLATFORM_VERSION, note="Compiler candidates are not MemoryEvents until committed.", items=window, **meta)


@router.get("/memory/compiler/candidates/{candidate_id}")
def memory_compiler_candidate_get(candidate_id: str):
    candidate = get_memory_compiler_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="memory_compiler_candidate_not_found")
    return {"version": PLATFORM_VERSION, "data": candidate}


@router.post("/memory/compiler/candidates/{candidate_id}/commit")
def memory_compiler_candidate_commit(candidate_id: str, body: MemoryCompilerCandidateCommitBody):
    candidate, event = commit_memory_compiler_candidate(candidate_id, metadata=body.metadata)
    return {
        "ok": True,
        "version": PLATFORM_VERSION,
        "note": "Candidate committed through append_memory_event; index and snapshot are ledger projections.",
        "data": candidate,
        "event": event,
    }


@router.post("/memory/retrieve/exact")
def memory_retrieve_exact(body: MemoryExactRetrievalBody):
    result = exact_retrieve(body.key_type, body.key, limit=body.limit, max_chars=body.max_chars)
    return {"ok": True, "version": PLATFORM_VERSION, "data": result}


@router.post("/memory/retrieve/search")
def memory_retrieve_search(body: MemoryEvidenceSearchBody):
    result = native_evidence_search(
        body.query,
        sources=body.sources,
        limit=body.limit,
        max_chars=body.max_chars,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": result}


@router.post("/memory/retrieve/runtime-context")
def memory_retrieve_runtime_context(body: MemoryRuntimeContextBody):
    result = build_runtime_memory_context(
        query=body.query,
        task_id=body.task_id,
        run_id=body.run_id,
        conversation_id=body.conversation_id,
        evidence_limit=body.evidence_limit,
        max_chars=body.max_chars,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": result}


@router.post("/memory/{memory_id}/events/supersede")
def memory_event_supersede(memory_id: str, body: MemoryEventAppendBody):
    if not memory_repo.get(memory_id):
        raise HTTPException(status_code=404, detail="memory_not_found")
    event = append_memory_event(
        event_type="superseded",
        memory_id=memory_id,
        subject_key=body.subject_key,
        content_json=body.content_json,
        value_json=body.value_json,
        evidence_refs=body.evidence_refs,
        supersedes_event_id=body.supersedes_event_id,
        created_by=body.created_by,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": event}


@router.post("/memory/{memory_id}/events/invalidate")
def memory_event_invalidate(memory_id: str, body: MemoryEventAppendBody):
    if not memory_repo.get(memory_id):
        raise HTTPException(status_code=404, detail="memory_not_found")
    event = append_memory_event(
        event_type="invalidated",
        memory_id=memory_id,
        subject_key=body.subject_key,
        content_json=body.content_json,
        value_json=body.value_json,
        evidence_refs=body.evidence_refs,
        invalidates_event_id=body.invalidates_event_id,
        created_by=body.created_by,
        metadata=body.metadata,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": event}


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
    record_memory_item_event(updated, event_type="user_approved", created_by="user")
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
    record_memory_item_event(updated, event_type="user_rejected", created_by="user")
    return {"ok": True, "version": PLATFORM_VERSION, "note": "Optional API token in production; audit via GET /audit/export", "data": updated}


@router.post("/memory/{memory_id}/rewrite")
def memory_rewrite(memory_id: str, body: MemoryRewriteBody):
    updated = user_rewrite_memory(
        memory_id,
        title=body.title,
        content=body.content,
        status=body.status,
        tags=body.tags,
        reason=body.reason,
    )
    return {"ok": True, "version": PLATFORM_VERSION, "data": updated}


@router.post("/memory/purge")
def memory_purge(body: MemoryPurgeBody):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="purge_requires_confirm_true")
    result = user_purge_memory(
        memory_ids=body.memory_ids,
        include_ledger=body.include_ledger,
        reason=body.reason,
    )
    return {"ok": True, "version": PLATFORM_VERSION, **result}


@router.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    m = memory_repo.get(memory_id)
    if not m:
        raise HTTPException(status_code=404, detail="memory_not_found")
    user_delete_memory(memory_id)
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
    probe = probe_local_bridge_detailed()
    m = build_metrics(bridge_probe=probe)
    lb = m.get("local_bridge", {})
    bridge_agents = local_bridge_repo.list()
    bridge_agents.sort(key=lambda x: x.last_seen_at, reverse=True)
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
    return {"version": PLATFORM_VERSION, "data": probe_local_bridge_detailed(fresh=True)}


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

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ListResponse(BaseModel):
    """List endpoints: persisted file/DB data."""

    version: str = "1.1.0"
    note: str | None = None
    items: list[Any] = Field(default_factory=list)
    # Phase 5 pagination metadata (optional; null on un-paginated responses).
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class AgentStatus(str, Enum):
    idle = "idle"
    running = "running"
    stalled = "stalled"
    offline = "offline"
    degraded = "degraded"


class AgentCapabilities(BaseModel):
    can_chat: bool = True
    can_code: bool = False
    can_browse: bool = False
    can_use_skills: bool = True
    can_generate_images: bool = False
    can_run_local_commands: bool = False
    can_stream: bool = False
    supports_structured_task: bool = False
    supports_mobile_input: bool = False
    supports_handoff: bool = False
    supports_callback: bool = False


class AgentControlPlaneConfig(BaseModel):
    """Persisted operator configuration for the Local Agent control plane."""

    model_config = ConfigDict(extra="allow")

    webhook_url: str | None = None
    cli_path: str | None = None
    callback_public_base_url: str | None = None
    working_directory: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    bridge_route: str | None = Field(default="/v1/execute")
    auth_mode: Literal["none", "bridge_shared_secret", "bearer"] | None = None
    bridge_timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=900,
        description="Per-agent bridge execution timeout override.",
    )
    bridge_retry_limit: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Per-agent bridge retry limit for transient bridge failures.",
    )
    callback_source_allowlist: list[str] = Field(
        default_factory=list,
        description="Allowed callback integration_path values for this agent. Empty means no extra restriction.",
    )
    shell_command: str | None = Field(
        default=None,
        description="For adapter_id=local_script: shell command executed on the Bridge host.",
    )
    allow_local_script: bool = Field(
        default=False,
        description="Must be true for local_script adapter to execute on Bridge (opt-in).",
    )


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    display_name: str
    type: Literal["builtin", "external"] = "builtin"
    status: AgentStatus = AgentStatus.idle
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    last_heartbeat_at: str | None = None
    # Adapters: builtin_octopus | claude_code | cursor_cli | openclaw_http | local_script
    adapter_id: str | None = None
    integration_mode: Literal["embedded", "external"] | None = None
    integration_channels: list[str] = Field(default_factory=list)
    control_depth: Literal["full", "partial", "assisted", "observe_only"] | None = None
    control_plane: AgentControlPlaneConfig | None = None
    # 启用开关：禁用后不会被调度执行，但保留配置与历史
    enabled: bool = True
    bound_skill_ids: list[str] = Field(
        default_factory=list,
        description="Platform skill_ids enabled for this agent.",
    )


class TaskStatus(str, Enum):
    created = "created"
    queued = "queued"
    assigned = "assigned"
    running = "running"
    waiting_approval = "waiting_approval"
    stalled = "stalled"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    title: str
    description: str | None = None
    execution_mode: Literal["commander", "pilot", "direct_agent"] = "commander"
    queue_priority: Literal["low", "normal", "high", "urgent"] = "normal"
    status: TaskStatus
    assigned_agent_id: str | None = None
    created_at: str
    updated_at: str | None = None
    retry_count: int = 0
    last_run_id: str | None = None
    last_error: str | None = None
    result_summary: str | None = None
    result_payload: dict[str, Any] | None = None
    # Approval/plan hooks (file-backed). Kept optional for backward compatibility.
    pending_approval_id: str | None = None
    execution_plan_id: str | None = None
    correlation_id: str | None = None
    source_task_id: str | None = None
    needs_attention: bool = False
    attention_reason: str | None = None
    recovery_attempt_count: int = 0
    max_recovery_attempts: int = 2


class TaskAssignment(BaseModel):
    assignment_id: str
    task_id: str
    agent_id: str
    assigned_at: str
    assigned_by: str = "operator"
    note: str | None = None
    active: bool = True


class Skill(BaseModel):
    skill_id: str
    name: str
    version: str
    category: str
    description: str | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    default_execution_policy: Literal["auto", "notify", "confirm"] = "confirm"
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None
    # Stable engineering fields (optional for backward compatibility)
    owner: str | None = None
    timeout_s: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # Inline schema may be stored as dict (no external schema registry yet)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    # Skill 母线：平台公共 vs 单 Agent 私有
    skill_scope: Literal["platform", "agent_private"] = "platform"
    owner_agent_id: str | None = None  # 私有时指向哪个 Agent
    # 启用状态（禁用后依然可见但不会被调用）
    enabled: bool = True


class Account(BaseModel):
    account_id: str
    provider: str
    display_name: str
    credential_type: str
    scopes: list[str] = Field(default_factory=list)
    status: Literal["active", "expired", "revoked", "unknown"] = "unknown"
    expires_at: str | None = None
    last_used_at: str | None = None


class Credential(BaseModel):
    credential_id: str
    account_id: str
    provider: str
    credential_type: str
    status: Literal["active", "expired", "revoked", "unknown"] = "unknown"
    created_at: str
    updated_at: str | None = None
    secret_material: str | None = None
    # Stable engineering: reference handle for tasks/skills (defaults to credential_id)
    credential_ref: str | None = None
    masked_hint: str | None = None


class CredentialUpsertBody(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)
    credential_type: str = Field(min_length=1, max_length=100)
    # secret is write-only; never returned
    secret_material: str = Field(min_length=1, max_length=5000)
    credential_ref: str | None = Field(default=None, max_length=200)
    masked_hint: str | None = Field(default=None, max_length=200)


class MemoryItem(BaseModel):
    memory_id: str
    memory_type: str
    title: str
    content: str
    confidence: float = 0.4
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    source_type: str | None = None
    source_id: str | None = None
    scope_type: Literal["personal", "task", "project", "conversation", "agent_working"] | None = None
    scope_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    # PRD §10 记忆 Tag 体系（治理字段）
    source_agent_id: str | None = None     # 由哪个 Agent 写入
    task_id: str | None = None             # 关联任务（可选）
    conversation_id: str | None = None     # 关联会话（可选）
    created_at: str | None = None          # 写入时间戳


class ConversationStatus(str, Enum):
    active = "active"
    archived = "archived"


class Conversation(BaseModel):
    conversation_id: str
    title: str
    agent_id: str
    status: ConversationStatus = ConversationStatus.active
    created_at: str
    updated_at: str | None = None
    last_message_at: str | None = None
    promoted_task_id: str | None = None


class ConversationMessage(BaseModel):
    message_id: str
    conversation_id: str
    role: Literal["system", "user", "assistant"] = "user"
    kind: Literal["chat", "file_read", "memory_search", "promotion_note", "system_note"] = "chat"
    content: str
    agent_id: str | None = None
    created_at: str
    references: list[dict[str, Any]] = Field(default_factory=list)
    create_memory_candidate: bool = False


class WatchdogSummary(BaseModel):
    running_tasks: int = 0
    stalled_tasks: int = 0
    failed_tasks_recent: int = 0
    stalled_agents: int = 0
    offline_agents: int = 0
    degraded_agents: int = 0
    bridge_reachable: bool | None = None
    waiting_handoffs: int = 0
    open_issues: int = 0
    escalated_issues: int = 0
    last_run_finished_at: str | None = None
    last_agent_heartbeat_at: str | None = None


class WatchdogEvent(BaseModel):
    event_id: str
    type: str
    message: str | None = None
    created_at: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    occurrence_count: int = 1
    severity: Literal["info", "warn", "error"] = "info"
    task_id: str | None = None
    agent_id: str | None = None
    recovery_hint: str | None = None
    correlation_id: str | None = None
    source: Literal["watchdog", "fixer", "human", "advisor"] | None = None
    issue_status: Literal["open", "processing", "resolved", "escalated"] | None = None
    suggested_action: str | None = None
    recovery_action: str | None = None
    recovery_result: str | None = None
    raw_error: str | None = None
    normalized_issue_signature: str | None = None
    issue_class: str | None = None
    related_run_id: str | None = None
    parent_run_id: str | None = None


class WatchdogStatus(BaseModel):
    summary: WatchdogSummary = Field(default_factory=WatchdogSummary)
    events: list[WatchdogEvent] = Field(default_factory=list)
    recovery_hints: list[str] = Field(default_factory=list)
    latest_issues: list[WatchdogEvent] = Field(default_factory=list)


class ObserverPattern(BaseModel):
    key: str
    count: int = 0
    latest_at: str | None = None
    summary: str | None = None
    related_agent_id: str | None = None


class ObserverPacket(BaseModel):
    packet_id: str
    task_id: str
    run_id: str | None = None
    correlation_id: str | None = None
    agent_id: str | None = None
    status: str
    execution_mode: str | None = None
    queue_priority: str | None = None
    integration_path: str | None = None
    error: str | None = None
    summary: str | None = None
    issue_class: str | None = None
    recovery_state: str | None = None
    created_at: str
    time_basis: Literal["finished_at", "started_at", "queued_at", "task_updated_at", "task_created_at"] | None = None


class ObserverSummary(BaseModel):
    generated_at: str
    recent_packets: list[ObserverPacket] = Field(default_factory=list)
    failure_patterns: list[ObserverPattern] = Field(default_factory=list)
    success_patterns: list[ObserverPattern] = Field(default_factory=list)
    recovery_patterns: list[ObserverPattern] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)


class AdvisorSuggestion(BaseModel):
    suggestion_id: str
    suggestion_type: Literal[
        "recovery_suggestion",
        "failure_pattern",
        "best_practice_candidate",
        "policy_draft_suggestion",
    ]
    target_type: Literal["platform", "task", "run", "skill", "policy", "agent", "bridge", "watchdog"]
    target_id: str
    issue_class: str | None = None
    pattern_key: str | None = None
    title: str
    summary: str
    rationale: str
    recommended_action: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["open", "accepted", "dismissed", "expired"] = "open"
    severity: Literal["info", "warning", "critical"] = "warning"
    confidence: Literal["low", "medium", "high"] | None = None
    requires_confirmation: bool = False
    occurrence_count: int | None = None
    affected_targets: int | None = None
    last_seen_at: str | None = None
    policy_preview: dict[str, Any] | None = None
    created_at: str
    updated_at: str | None = None
    correlation_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None
    source_watchdog_event_id: str | None = None
    # P2-C: acceptance path hints (populated when operator accepts)
    next_action_hint: str | None = None
    next_action_url: str | None = None


# ── P3 Governor Layer ────────────────────────────────────────────────────────

_GOVERNOR_ALLOWLIST = frozenset(
    ["retry_run", "acknowledge_escalation", "resolve_escalation", "adjust_queue_priority"]
)


class GovernableAction(BaseModel):
    """A candidate action built from an AdvisorSuggestion, ready for gate evaluation."""

    model_config = ConfigDict(extra="ignore")

    action_id: str
    suggestion_id: str
    action_type: Literal[
        "retry_run", "acknowledge_escalation", "resolve_escalation", "adjust_queue_priority"
    ]
    target_type: str          # "task" | "watchdog_event"
    target_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "medium"
    idempotency_key: str
    created_at: str
    correlation_id: str | None = None


class GovernorDecision(BaseModel):
    """Gate evaluation result.  status flows: pending → confirmed/executed/denied/failed."""

    model_config = ConfigDict(extra="ignore")

    decision_id: str
    action_id: str
    suggestion_id: str
    decision: Literal["auto_execute", "require_confirmation", "deny"]
    reason: str
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"]
    gates_passed: list[str] = Field(default_factory=list)
    gates_failed: list[str] = Field(default_factory=list)
    status: Literal["pending", "confirmed", "executed", "denied", "failed"] = "pending"
    created_at: str
    executed_at: str | None = None
    confirmed_by: str | None = None
    correlation_id: str | None = None
    source_task_id: str | None = None
    source_watchdog_event_id: str | None = None


class ExecutionReceipt(BaseModel):
    """Immutable audit record produced after a Governor action is executed."""

    model_config = ConfigDict(extra="ignore")

    receipt_id: str
    decision_id: str
    action_id: str
    suggestion_id: str
    action_type: str
    target_id: str
    outcome: Literal["succeeded", "failed", "skipped_duplicate"]
    error: str | None = None
    result_summary: str | None = None
    executed_at: str
    idempotency_key: str
    correlation_id: str | None = None


class GovernorEvaluateBody(BaseModel):
    suggestion_id: str = Field(min_length=1)
    action_type: Literal[
        "retry_run", "acknowledge_escalation", "resolve_escalation", "adjust_queue_priority"
    ]
    target_id: str = Field(min_length=1)
    target_type: str = Field(default="task")
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutionPolicy(BaseModel):
    policy_id: str
    scope: Literal["global", "agent", "skill", "account"] = "global"
    target_id: str | None = None
    mode: Literal["auto", "notify", "confirm"] = "confirm"
    note: str | None = None
    # Draft policies are not enforced; is_draft=false means enforceable.
    is_draft: bool = True

    @model_validator(mode="before")
    @classmethod
    def _legacy_is_mock_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "is_mock" in d and "is_draft" not in d:
                d["is_draft"] = d.pop("is_mock")
            return d
        return data


class ExecutionPolicyUpsertBody(BaseModel):
    policy_id: str = Field(min_length=1, max_length=200)
    scope: Literal["global", "agent", "skill", "account"] = "global"
    target_id: str | None = None
    mode: Literal["auto", "notify", "confirm"] = "confirm"
    note: str | None = None
    # Setting is_draft=false makes this policy enforceable by policy_engine.
    is_draft: bool = False

    @model_validator(mode="before")
    @classmethod
    def _legacy_is_mock_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "is_mock" in d and "is_draft" not in d:
                d["is_draft"] = d.pop("is_mock")
            return d
        return data


class PolicyExplanation(BaseModel):
    scope: Literal["global", "agent", "skill", "account"]
    target_id: str | None = None
    effective_mode: Literal["auto", "notify", "confirm"]
    policy_source: Literal["enforced_policy", "skill_default", "implicit_default"] = "implicit_default"
    matched_policy_id: str | None = None
    matched_policy_scope: Literal["global", "agent", "skill", "account"] | None = None
    default_mode: Literal["auto", "notify", "confirm"] | None = None
    reason: str | None = None
    precedence: list[str] = Field(default_factory=list)
    note: str | None = None


class EscalationActionBody(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class Report(BaseModel):
    report_id: str
    type: str
    title: str
    created_at: str
    content: str
    is_draft: bool = True

    @model_validator(mode="before")
    @classmethod
    def _legacy_is_mock_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "is_mock" in d and "is_draft" not in d:
                d["is_draft"] = d.pop("is_mock")
            return d
        return data


# --- File artifacts ---


class FileArtifact(BaseModel):
    """
    轻量「文件空间」登记：平台、任务、Agent、用户产出的文件制品。

    仅存元数据（路径 / 大小 / 来源 / 关联任务），
    不负责实际文件传输与加密。实际文件落在用户本地或 Local Bridge 宿主机。
    """

    file_id: str
    name: str
    path: str | None = None  # 绝对路径或 URL；nullable 时表示已删除但保留记录
    mime_type: str | None = None
    size_bytes: int | None = None
    source: Literal["task", "agent", "user", "bridge"] = "user"
    source_id: str | None = None  # 产出源 ID（task_id / agent_id 等）
    task_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str


class FileArtifactCreateBody(BaseModel):
    name: str
    path: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    source: Literal["task", "agent", "user", "bridge"] = "user"
    source_id: str | None = None
    task_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


# --- Task lifecycle ---


class TaskEventRecord(BaseModel):
    event_id: str
    task_id: str
    type: str
    message: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str
    correlation_id: str | None = None


class Run(BaseModel):
    run_id: str
    task_id: str
    agent_id: str | None = None
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"  # pending == queued
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    integration_path: str | None = None
    output_excerpt: str | None = None
    correlation_id: str | None = None
    parent_run_id: str | None = None
    input_snapshot: dict[str, Any] | None = None
    output_snapshot: dict[str, Any] | None = None
    environment_summary: dict[str, Any] | None = None
    callback_summary: dict[str, Any] | None = None
    claimed_at: str | None = None
    claim_token: str | None = None


class RunLogLine(BaseModel):
    log_id: str
    run_id: str
    seq: int
    level: Literal["info", "warn", "error", "debug"] = "info"
    message: str
    meta: dict[str, Any] | None = None
    created_at: str
    correlation_id: str | None = None


class ProcessedActionReceipt(BaseModel):
    receipt_id: str
    action_type: Literal[
        "run_request",
        "retry_request",
        "bridge_callback",
        "watchdog_issue",
        "fixer_action",
        "idempotency_api",
    ]
    key: str
    task_id: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    status: Literal["claimed", "completed", "failed", "duplicate", "late_callback", "rejected"] = "claimed"
    result_ref: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str
    claimed_at: str | None = None
    claim_ttl_seconds: int = 30
    updated_at: str | None = None


# --- Commander / Pilot / Direct-agent gating ---


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ApprovalKind(str, Enum):
    policy_gate = "policy_gate"
    pilot_step = "pilot_step"
    external_handoff = "external_handoff"


class TaskApproval(BaseModel):
    approval_id: str
    task_id: str
    kind: ApprovalKind
    status: ApprovalStatus = ApprovalStatus.pending
    requested_at: str
    decided_at: str | None = None
    requested_by: str = "system"
    decided_by: str | None = None
    reason: str | None = None
    # For pilot steps / external flows
    meta: dict[str, Any] | None = None


class ExecutionStepStatus(str, Enum):
    pending = "pending"
    done = "done"
    skipped = "skipped"
    failed = "failed"


class ExecutionStep(BaseModel):
    step_id: str
    kind: Literal["plan", "execute", "summarize"]
    status: ExecutionStepStatus = ExecutionStepStatus.pending
    created_at: str
    updated_at: str | None = None
    payload: dict[str, Any] | None = None


class ExecutionPlan(BaseModel):
    plan_id: str
    task_id: str
    mode: Literal["pilot"] = "pilot"
    created_at: str
    updated_at: str | None = None
    steps: list[ExecutionStep] = Field(default_factory=list)


class TaskApproveBody(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class TaskRejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=5000)


# --- Notifications ---


class NotificationChannelType(str, Enum):
    webhook = "webhook"


class NotificationChannel(BaseModel):
    channel_id: str
    type: NotificationChannelType = NotificationChannelType.webhook
    enabled: bool = False
    name: str | None = None
    webhook_url: str | None = None
    created_at: str
    updated_at: str | None = None


class NotificationDelivery(BaseModel):
    delivery_id: str
    channel_id: str
    event_id: str
    event_type: str
    created_at: str
    status: Literal["succeeded", "failed"] = "failed"
    error: str | None = None
    meta: dict[str, Any] | None = None


class NotificationChannelUpsertBody(BaseModel):
    channel_id: str = Field(min_length=1, max_length=200)
    enabled: bool = False
    name: str | None = Field(default=None, max_length=200)
    webhook_url: str | None = Field(default=None, max_length=5000)


# --- Agent API Profiles (configuration center) ---


class ApiProvider(str, Enum):
    openai_compatible = "openai_compatible"
    anthropic_compatible = "anthropic_compatible"


class AgentApiProfile(BaseModel):
    """
    Stored in file store. `api_key` is write-only from the UI perspective:
    - API may accept it in POST body
    - API never returns it in responses (masked)
    """

    profile_id: str
    name: str
    provider: ApiProvider = ApiProvider.openai_compatible
    base_url: str
    model: str
    api_key: str | None = None
    created_at: str
    updated_at: str | None = None
    is_default: bool = False


class AgentApiBinding(BaseModel):
    binding_id: str
    agent_id: str
    profile_id: str
    created_at: str
    updated_at: str | None = None


class AgentApiProfileUpsertBody(BaseModel):
    profile_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    provider: ApiProvider = ApiProvider.openai_compatible
    base_url: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=5000)
    is_default: bool = False


class AgentApiBindingBody(BaseModel):
    profile_id: str = Field(min_length=1, max_length=200)


class SkillExecuteBody(BaseModel):
    """
    Execute a skill.
    If task_id/run_id are provided, Octopus will append audit events/logs.
    """

    input: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None


class SkillPatchBody(BaseModel):
    """Partial update for a Skill (only enabled state for now)."""

    enabled: bool | None = None
    default_execution_policy: Literal["auto", "notify", "confirm"] | None = None
    description: str | None = Field(default=None, max_length=5000)


class SkillExecuteResult(BaseModel):
    ok: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    execution_mode: Literal["commander", "pilot", "direct_agent"] = "commander"
    queue_priority: Literal["low", "normal", "high", "urgent"] = "normal"
    source_task_id: str | None = Field(default=None, max_length=200)


class ConversationCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    agent_id: str = Field(min_length=1)


class ConversationPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    agent_id: str | None = Field(default=None, min_length=1)


class ConversationMessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    kind: Literal["chat", "file_read", "memory_search"] = "chat"
    file_path: str | None = Field(default=None, max_length=2000)
    create_memory_candidate: bool = False


class ConversationPromoteBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    execution_mode: Literal["commander", "pilot", "direct_agent"] = "commander"
    assign_agent: bool = True


class TaskAssignBody(BaseModel):
    agent_id: str = Field(min_length=1)


class TaskFailBody(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class BridgeCompleteBody(BaseModel):
    task_id: str
    run_id: str
    status: Literal["succeeded", "failed"]
    output: str | None = None
    error: str | None = None
    integration_path: str | None = Field(default="bridge_callback")


class LocalBridgeRegisterBody(BaseModel):
    agent_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=500)
    adapter_id: str = Field(min_length=1, max_length=100)
    bridge_id: str = Field(default="local_bridge")
    capabilities: dict[str, bool] = Field(default_factory=dict)
    workspace_path: str | None = None
    status: Literal["online", "idle", "running", "offline", "degraded"] = "online"
    last_seen_at: str | None = None


class AgentCreateBody(BaseModel):
    agent_id: str | None = Field(default=None, max_length=200)
    display_name: str = Field(min_length=1, max_length=500)
    type: Literal["builtin", "external"] = "external"
    adapter_id: str = Field(min_length=1, max_length=100)
    integration_mode: Literal["embedded", "external"]
    integration_channels: list[str] = Field(default_factory=list)
    control_depth: Literal["full", "partial", "assisted", "observe_only"]
    capabilities: AgentCapabilities | None = None
    control_plane: AgentControlPlaneConfig | None = None


class AgentPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=500)
    adapter_id: str | None = Field(default=None, max_length=100)
    integration_mode: Literal["embedded", "external"] | None = None
    integration_channels: list[str] | None = None
    control_depth: Literal["full", "partial", "assisted", "observe_only"] | None = None
    capabilities: AgentCapabilities | None = None
    control_plane: AgentControlPlaneConfig | None = None
    enabled: bool | None = None
    bound_skill_ids: list[str] | None = None


class LocalBridgeAgentState(BaseModel):
    state_id: str
    bridge_id: str
    agent_id: str
    display_name: str
    adapter_id: str
    capabilities: dict[str, bool] = Field(default_factory=dict)
    workspace_path: str | None = None
    status: Literal["online", "idle", "running", "offline", "degraded"] = "online"
    registered_at: str
    last_seen_at: str
    last_task_id: str | None = None
    last_run_id: str | None = None
    last_result_status: Literal["pending", "succeeded", "failed"] | None = None
    last_error: str | None = None


class LocalBridgeResultBody(BaseModel):
    task_id: str
    run_id: str
    agent_id: str
    status: Literal["succeeded", "failed"]
    output: str | None = None
    error: str | None = None
    integration_path: str | None = Field(default="local_bridge_result")
    result_meta: dict[str, Any] | None = None


class ClaudeAdapterDispatchBody(BaseModel):
    """Kanaloa → Claude Code adapter bridge (dry-run default)."""

    task: str = Field(min_length=1, max_length=8000)
    workspace: str | None = Field(default=None, max_length=2000)
    mode: Literal["dry_run", "execute"] = "dry_run"
    constraints: dict[str, Any] = Field(default_factory=dict)


class KanaloaCreateTaskBody(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=20000)
    mode: Literal["dry_run", "execute"] = "execute"
    workspace: str | None = Field(default=None, max_length=2000)


class KanaloaDispatchBody(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)


class KanaloaCancelBody(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)


# ── P3 Kanaloa Orchestrator Runtime ──────────────────────────────────────────


class OrchestratorSubtaskRecord(BaseModel):
    """One planned unit of work inside a master orchestration run."""

    subtask_id: str
    master_task_id: str
    title: str
    instruction: str
    kind: str = Field(
        default="code_audit",
        description="code_audit|code_fix|repo_status|frontend_check|external_http_task|cursor_task|verification|summarize|unknown",
    )
    target_agent_id: str | None = None
    target_adapter_id: str | None = None
    status: Literal["pending", "running", "blocked", "failed", "completed", "skipped"] = "pending"
    attempt_count: int = 0
    result_summary: str | None = None
    platform_task_id: str | None = None
    last_run_id: str | None = None
    error: str | None = None
    command_key: str | None = Field(default=None, description="verification_runner hint")
    created_at: str
    updated_at: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class OrchestratorMasterTask(BaseModel):
    """Persisted master orchestration record (subtasks + timeline)."""

    master_task_id: str
    user_instruction: str
    status: Literal["pending", "queued", "running", "blocked", "failed", "completed", "cancelled"] = "pending"
    subtasks: list[OrchestratorSubtaskRecord] = Field(default_factory=list)
    selected_agents: dict[str, str] = Field(default_factory=dict)
    verification_status: str | None = None
    verification_results: list[dict[str, Any]] = Field(default_factory=list)
    final_summary: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str | None = None
    conversation_id: str | None = None
    created_at: str
    updated_at: str | None = None
    started_run_at: str | None = None
    completed_at: str | None = None


class KanaloaOrchestratorRunBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = Field(default=None, max_length=200)
    """If dry_run, subtasks enqueue plan-only tasks (no worker run). Owner tests often use dry_run."""
    subtask_mode: Literal["dry_run", "execute"] = "execute"


class KanaloaOrchestratorContinueBody(BaseModel):
    resume_from_subtask_id: str | None = Field(default=None, max_length=200)
    subtask_mode: Literal["dry_run", "execute"] = "execute"

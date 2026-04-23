from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ListResponse(BaseModel):
    """List endpoints: Beta uses real file store; `is_mock` kept for legacy seeds only."""

    is_mock: bool = False
    beta: bool = True
    note: str | None = None
    items: list[Any] = Field(default_factory=list)


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
    """Persisted operator configuration for the Local Agent control plane (Beta)."""

    model_config = ConfigDict(extra="allow")

    webhook_url: str | None = None
    cli_path: str | None = None
    callback_public_base_url: str | None = None
    working_directory: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    bridge_route: str | None = Field(default="/v1/execute")
    auth_mode: Literal["none", "bridge_shared_secret", "bearer"] | None = None
    shell_command: str | None = Field(
        default=None,
        description="For adapter_id=local_script: shell command executed on the Bridge host.",
    )


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_id: str
    display_name: str
    type: Literal["builtin", "external"] = "builtin"
    status: AgentStatus = AgentStatus.idle
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    last_heartbeat_at: str | None = None
    # Beta: builtin_octopus | claude_code | cursor_cli | openclaw_http | local_script
    adapter_id: str | None = None
    integration_mode: Literal["embedded", "external"] | None = None
    integration_channels: list[str] = Field(default_factory=list)
    control_depth: Literal["full", "partial", "assisted", "observe_only"] | None = None
    control_plane: AgentControlPlaneConfig | None = None
    # 启用开关：禁用后不会被调度执行，但保留配置与历史
    enabled: bool = True


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
    status: TaskStatus
    assigned_agent_id: str | None = None
    created_at: str
    updated_at: str | None = None
    retry_count: int = 0
    last_run_id: str | None = None
    last_error: str | None = None
    result_summary: str | None = None
    result_payload: dict[str, Any] | None = None
    # Beta: approval/plan hooks (file-backed). Kept optional for backward compatibility.
    pending_approval_id: str | None = None
    execution_plan_id: str | None = None


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
    # Beta: inline schema may be stored as dict (no external schema registry yet)
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
    last_run_finished_at: str | None = None
    last_agent_heartbeat_at: str | None = None


class WatchdogEvent(BaseModel):
    event_id: str
    type: str
    message: str | None = None
    created_at: str
    severity: Literal["info", "warn", "error"] = "info"
    task_id: str | None = None
    agent_id: str | None = None
    recovery_hint: str | None = None


class WatchdogStatus(BaseModel):
    summary: WatchdogSummary = Field(default_factory=WatchdogSummary)
    events: list[WatchdogEvent] = Field(default_factory=list)
    recovery_hints: list[str] = Field(default_factory=list)


class ExecutionPolicy(BaseModel):
    policy_id: str
    scope: Literal["global", "agent", "skill", "account"] = "global"
    target_id: str | None = None
    mode: Literal["auto", "notify", "confirm"] = "confirm"
    note: str | None = None
    is_mock: bool = True


class ExecutionPolicyUpsertBody(BaseModel):
    policy_id: str = Field(min_length=1, max_length=200)
    scope: Literal["global", "agent", "skill", "account"] = "global"
    target_id: str | None = None
    mode: Literal["auto", "notify", "confirm"] = "confirm"
    note: str | None = None
    # Setting is_mock=false makes this policy enforceable.
    is_mock: bool = False


class Report(BaseModel):
    report_id: str
    type: str
    title: str
    created_at: str
    content: str
    is_mock: bool = True


# --- File artifacts (Beta) ---


class FileArtifact(BaseModel):
    """
    轻量「文件空间」登记：平台、任务、Agent、用户产出的文件制品。

    Beta 阶段只存元数据（路径 / 大小 / 来源 / 关联任务），
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


# --- Task lifecycle (Beta) ---


class TaskEventRecord(BaseModel):
    event_id: str
    task_id: str
    type: str
    message: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str


class Run(BaseModel):
    run_id: str
    task_id: str
    agent_id: str | None = None
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"  # pending == queued
    queued_at: str | None = None
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    integration_path: str | None = None
    output_excerpt: str | None = None


class RunLogLine(BaseModel):
    log_id: str
    run_id: str
    seq: int
    level: Literal["info", "warn", "error", "debug"] = "info"
    message: str
    meta: dict[str, Any] | None = None
    created_at: str


# --- Commander / Pilot / Direct-agent gating (Beta → stable core) ---


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


# --- Notifications (beta ops) ---


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


# --- Agent API Profiles (beta configuration center) ---


class ApiProvider(str, Enum):
    openai_compatible = "openai_compatible"
    anthropic_compatible = "anthropic_compatible"


class AgentApiProfile(BaseModel):
    """
    Beta: stored in file store. `api_key` is write-only from the UI perspective:
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
    Execute a skill (beta execution surface).
    If task_id/run_id are provided, Octopus will append audit events/logs.
    """

    input: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None


class SkillPatchBody(BaseModel):
    """Partial update for a Skill (beta: only enabled state for now)."""

    enabled: bool | None = None


class SkillExecuteResult(BaseModel):
    ok: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    execution_mode: Literal["commander", "pilot", "direct_agent"] = "commander"


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

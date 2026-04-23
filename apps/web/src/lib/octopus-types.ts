export type ListResponse<T> = {
  is_mock: boolean;
  beta?: boolean;
  note?: string;
  items: T[];
};

export type AgentControlPlaneConfig = {
  webhook_url?: string | null;
  cli_path?: string | null;
  callback_public_base_url?: string | null;
  working_directory?: string | null;
  env?: Record<string, string>;
  bridge_route?: string | null;
  auth_mode?: "none" | "bridge_shared_secret" | "bearer" | null;
  shell_command?: string | null;
};

export type Agent = {
  agent_id: string;
  display_name: string;
  type: "builtin" | "external";
  status: "idle" | "running" | "stalled" | "offline" | "degraded";
  adapter_id?: string | null;
  last_heartbeat_at?: string | null;
  capabilities: Record<string, boolean>;
  integration_mode?: "embedded" | "external" | null;
  integration_channels?: string[];
  control_depth?: "full" | "partial" | "assisted" | "observe_only" | null;
  control_plane?: AgentControlPlaneConfig | null;
  /** 禁用后平台不会再调度此 Agent（保留历史）。内置 Kanaloa 只能禁用不能删除。 */
  enabled?: boolean;
};

export type ApiProfile = {
  profile_id: string;
  name: string;
  provider: "openai_compatible" | "anthropic_compatible";
  base_url: string;
  model: string;
  api_key?: string | null; // masked or null in API responses
  created_at: string;
  updated_at?: string | null;
  is_default: boolean;
};

export type Task = {
  task_id: string;
  title: string;
  description?: string | null;
  execution_mode: "commander" | "pilot" | "direct_agent";
  status:
    | "created"
    | "queued"
    | "assigned"
    | "running"
    | "waiting_approval"
    | "stalled"
    | "succeeded"
    | "failed"
    | "cancelled"
    | "expired";
  assigned_agent_id?: string | null;
  created_at: string;
  updated_at?: string | null;
  retry_count: number;
  last_run_id?: string | null;
  last_error?: string | null;
  result_summary?: string | null;
  result_payload?: Record<string, unknown> | null;
  pending_approval_id?: string | null;
  execution_plan_id?: string | null;
};

export type ExecutionStep = {
  step_id: string;
  kind: "plan" | "execute" | "summarize";
  status: "pending" | "done" | "skipped" | "failed";
  created_at: string;
  updated_at?: string | null;
  payload?: Record<string, unknown> | null;
};

export type ExecutionPlan = {
  plan_id: string;
  task_id: string;
  mode: "pilot";
  created_at: string;
  updated_at?: string | null;
  steps: ExecutionStep[];
};

export type TaskAssignment = {
  assignment_id: string;
  task_id: string;
  agent_id: string;
  assigned_at: string;
  assigned_by: string;
  note?: string | null;
  active: boolean;
};

export type Conversation = {
  conversation_id: string;
  title: string;
  agent_id: string;
  status: "active" | "archived";
  created_at: string;
  updated_at?: string | null;
  last_message_at?: string | null;
  promoted_task_id?: string | null;
};

export type ConversationMessage = {
  message_id: string;
  conversation_id: string;
  role: "system" | "user" | "assistant";
  kind: "chat" | "file_read" | "memory_search" | "promotion_note" | "system_note";
  content: string;
  agent_id?: string | null;
  created_at: string;
  references: Array<Record<string, unknown>>;
  create_memory_candidate: boolean;
};

export type TaskEvent = {
  event_id: string;
  task_id: string;
  type: string;
  message?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
};

export type Run = {
  run_id: string;
  task_id: string;
  agent_id?: string | null;
  status: "pending" | "running" | "succeeded" | "failed";
  queued_at?: string | null;
  started_at: string;
  finished_at?: string | null;
  error?: string | null;
  integration_path?: string | null;
  output_excerpt?: string | null;
};

export type RunLogLine = {
  log_id: string;
  run_id: string;
  seq: number;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  meta?: Record<string, unknown> | null;
  created_at: string;
};

export type LocalBridgeAgentState = {
  state_id: string;
  bridge_id: string;
  agent_id: string;
  display_name: string;
  adapter_id: string;
  capabilities: Record<string, boolean>;
  workspace_path?: string | null;
  status: "online" | "idle" | "running" | "offline" | "degraded";
  registered_at: string;
  last_seen_at: string;
  last_task_id?: string | null;
  last_run_id?: string | null;
  last_result_status?: "pending" | "succeeded" | "failed" | null;
  last_error?: string | null;
};

export type MemoryItem = {
  memory_id: string;
  memory_type: string;
  title: string;
  content: string;
  confidence: number;
  status: "candidate" | "approved" | "rejected";
  source_type?: string | null;
  source_id?: string | null;
  scope_type?: "personal" | "task" | "project" | "conversation" | "agent_working" | null;
  scope_id?: string | null;
  tags: string[];
};

export type WatchdogEvent = {
  event_id: string;
  type: string;
  message?: string | null;
  created_at: string;
  severity: "info" | "warn" | "error";
  task_id?: string | null;
  agent_id?: string | null;
  recovery_hint?: string | null;
};

export type WatchdogStatus = {
  summary: {
    running_tasks: number;
    stalled_tasks: number;
    failed_tasks_recent: number;
    stalled_agents: number;
    offline_agents: number;
    degraded_agents: number;
    bridge_reachable: boolean | null;
    waiting_handoffs: number;
    last_run_finished_at?: string | null;
    last_agent_heartbeat_at?: string | null;
  };
  events: WatchdogEvent[];
  recovery_hints: string[];
};

export type ListResponse<T> = {
  version?: string;
  note?: string;
  items: T[];
  // Phase 5 pagination metadata (optional; older endpoints omit them).
  total?: number;
  limit?: number;
  offset?: number;
};

export type AgentControlPlaneConfig = {
  webhook_url?: string | null;
  cli_path?: string | null;
  callback_public_base_url?: string | null;
  working_directory?: string | null;
  env?: Record<string, string>;
  bridge_route?: string | null;
  auth_mode?: "none" | "bridge_shared_secret" | "bearer" | null;
  bridge_timeout_seconds?: number | null;
  bridge_retry_limit?: number | null;
  callback_source_allowlist?: string[];
  shell_command?: string | null;
  allow_local_script?: boolean;
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
  bound_skill_ids?: string[];
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
  queue_priority: "low" | "normal" | "high" | "urgent";
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
  correlation_id?: string | null;
  source_task_id?: string | null;
  needs_attention: boolean;
  attention_reason?: string | null;
  recovery_attempt_count: number;
  max_recovery_attempts: number;
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
  correlation_id?: string | null;
};

export type Run = {
  run_id: string;
  task_id: string;
  agent_id?: string | null;
  status: "pending" | "running" | "succeeded" | "failed";
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  integration_path?: string | null;
  output_excerpt?: string | null;
  correlation_id?: string | null;
  parent_run_id?: string | null;
  input_snapshot?: Record<string, unknown> | null;
  output_snapshot?: Record<string, unknown> | null;
  environment_summary?: Record<string, unknown> | null;
  callback_summary?: Record<string, unknown> | null;
};

export type RunStep = {
  run_step_id: string;
  run_id: string;
  task_id: string;
  sequence: number;
  step_type: "plan" | "execute" | "summarize" | "other";
  status: "pending" | "running" | "succeeded" | "failed" | "blocked" | "skipped";
  title?: string | null;
  parent_step_id?: string | null;
  agent_id?: string | null;
  skill_id?: string | null;
  tool_call_id?: string | null;
  decision_id?: string | null;
  failure_id?: string | null;
  input_context_ref?: string | null;
  output_ref?: string | null;
  verification_ref?: string | null;
  repair_ref?: string | null;
  evidence_refs: string[];
  memory_event_refs: string[];
  retry_count: number;
  retry_history: Array<Record<string, unknown>>;
  latest_failure_type?: string | null;
  attempt_index: number;
  created_at: string;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  correlation_id?: string | null;
  metadata: Record<string, unknown>;
};

export type ReferenceCandidate = {
  candidate_id: string;
  run_id: string;
  run_step_id: string;
  task_id: string;
  agent_role: string;
  summary: string;
  risks: string[];
  recommended_plan: string[];
  files_to_touch: string[];
  confidence: number;
  evidence_refs: string[];
  status: "proposed" | "selected" | "rejected";
  created_at: string;
  metadata: Record<string, unknown>;
};

export type AggregatorDecision = {
  aggregation_id: string;
  run_id: string;
  run_step_id: string;
  task_id: string;
  candidates_considered: string[];
  selected_plan: string[];
  rejected_candidates: Array<Record<string, unknown>>;
  consensus: string;
  conflicts: string[];
  confidence: number;
  known_gaps: string[];
  verifier_requirements: string[];
  requires_user_confirmation: boolean;
  evidence_refs: string[];
  created_at: string;
  metadata: Record<string, unknown>;
};

export type VerifierResult = {
  result_id: string;
  run_id: string;
  run_step_id: string;
  task_id: string;
  verifier_type: "code" | "docs" | "security" | "bridge" | "manual";
  status: "passed" | "failed" | "blocked" | "skipped";
  passed: boolean;
  findings: string[];
  command_key?: string | null;
  check_key?: string | null;
  output_summary?: string | null;
  error_summary?: string | null;
  evidence_refs: string[];
  created_at: string;
  metadata: Record<string, unknown>;
};

export type RepairAttempt = {
  repair_attempt_id: string;
  run_id: string;
  run_step_id: string;
  task_id: string;
  verifier_result_id: string;
  failure_id?: string | null;
  failure_ref?: string | null;
  failure_type: string;
  attempt_index: number;
  attempt_kind: "retry" | "repair" | "trace_rollback";
  status: string;
  repair_action: string;
  action_key?: string | null;
  repair_key?: string | null;
  loop_event?: string | null;
  needs_user_confirmation: boolean;
  high_risk: boolean;
  safety_status: "allowed" | "needs_user_confirmation" | "blocked";
  evidence_refs: string[];
  created_at: string;
  metadata: Record<string, unknown>;
};

export type MemoryCompilerRun = {
  compiler_run_id: string;
  scope_type: "run" | "task";
  scope_id: string;
  run_id?: string | null;
  task_id?: string | null;
  dry_run: boolean;
  status: "completed" | "failed";
  policy_name: string;
  candidates_created: number;
  candidates_committed: number;
  started_at: string;
  finished_at: string;
  metadata: Record<string, unknown>;
};

export type MemoryCompilerCandidate = {
  candidate_id: string;
  compiler_run_id: string;
  candidate_type: string;
  status: "proposed" | "committed" | "rejected" | "skipped";
  memory_id?: string | null;
  subject_key: string;
  scope_type?: string | null;
  scope_id?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  run_id?: string | null;
  run_step_id?: string | null;
  task_id?: string | null;
  conversation_id?: string | null;
  skill_id?: string | null;
  decision_id?: string | null;
  failure_id?: string | null;
  content_json: Record<string, unknown>;
  value_json: Record<string, unknown>;
  evidence_refs: string[];
  confidence?: number | null;
  policy_result: Record<string, unknown>;
  supersedes_event_id?: string | null;
  invalidates_event_id?: string | null;
  fingerprint: string;
  committed_event_id?: string | null;
  created_at: string;
  committed_at?: string | null;
  metadata: Record<string, unknown>;
};

export type MemoryEvent = {
  event_id: string;
  memory_id?: string | null;
  event_type: string;
  subject_key?: string | null;
  scope_type?: string | null;
  scope_id?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  run_id?: string | null;
  run_step_id?: string | null;
  task_id?: string | null;
  conversation_id?: string | null;
  skill_id?: string | null;
  decision_id?: string | null;
  failure_id?: string | null;
  content_json: Record<string, unknown>;
  value_json: Record<string, unknown>;
  evidence_refs: string[];
  confidence?: number | null;
  policy_result?: Record<string, unknown> | null;
  supersedes_event_id?: string | null;
  invalidates_event_id?: string | null;
  created_by: "ai" | "user" | "system";
  created_at: string;
  metadata: Record<string, unknown>;
};

export type MemoryIndexEntry = {
  index_id: string;
  memory_id: string;
  subject_key?: string | null;
  status: "candidate" | "active" | "rejected" | "superseded" | "invalidated" | "deleted" | "purged";
  memory_type?: string | null;
  title?: string | null;
  scope_type?: string | null;
  scope_id?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  latest_event_id?: string | null;
  tags: string[];
  updated_at: string;
  value_json: Record<string, unknown>;
};

export type ActiveMemorySnapshot = {
  snapshot_id: string;
  scope_type: string;
  scope_id: string;
  memory_ids: string[];
  event_ids: string[];
  value_json: Record<string, unknown>;
  updated_at: string;
};

export type RetrievalResult = {
  mode?: string;
  query?: string;
  key_type?: string;
  key?: string;
  items?: Array<Record<string, unknown>>;
  active_snapshot?: ActiveMemorySnapshot | null;
  relevant_evidence?: Array<Record<string, unknown>>;
  current_run_context?: Record<string, unknown> | null;
  used_chars?: number;
  max_chars?: number;
  truncated?: boolean;
  [key: string]: unknown;
};

export type RunLogLine = {
  log_id: string;
  run_id: string;
  seq: number;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  meta?: Record<string, unknown> | null;
  created_at: string;
  correlation_id?: string | null;
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
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  occurrence_count?: number;
  severity: "info" | "warn" | "error";
  task_id?: string | null;
  agent_id?: string | null;
  recovery_hint?: string | null;
  correlation_id?: string | null;
  source?: "watchdog" | "fixer" | "human" | "advisor" | null;
  issue_status?: "open" | "processing" | "resolved" | "escalated" | null;
  suggested_action?: string | null;
  recovery_action?: string | null;
  recovery_result?: string | null;
  raw_error?: string | null;
  normalized_issue_signature?: string | null;
  issue_class?: string | null;
  related_run_id?: string | null;
  parent_run_id?: string | null;
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
    open_issues: number;
    escalated_issues: number;
    last_run_finished_at?: string | null;
    last_agent_heartbeat_at?: string | null;
  };
  events: WatchdogEvent[];
  recovery_hints: string[];
  latest_issues?: WatchdogEvent[];
};

export type ObserverPattern = {
  key: string;
  count: number;
  latest_at?: string | null;
  summary?: string | null;
  related_agent_id?: string | null;
};

export type ObserverPacket = {
  packet_id: string;
  task_id: string;
  run_id?: string | null;
  correlation_id?: string | null;
  agent_id?: string | null;
  status: string;
  execution_mode?: string | null;
  queue_priority?: string | null;
  integration_path?: string | null;
  error?: string | null;
  summary?: string | null;
  issue_class?: string | null;
  recovery_state?: string | null;
  created_at: string;
  time_basis?: "finished_at" | "started_at" | "queued_at" | "task_updated_at" | "task_created_at" | null;
};

export type ObserverSummary = {
  generated_at: string;
  recent_packets: ObserverPacket[];
  failure_patterns: ObserverPattern[];
  success_patterns: ObserverPattern[];
  recovery_patterns: ObserverPattern[];
  totals: Record<string, number>;
};

export type PolicyExplanation = {
  scope: "global" | "agent" | "skill" | "account";
  target_id?: string | null;
  effective_mode: "auto" | "notify" | "confirm";
  policy_source: "enforced_policy" | "skill_default" | "implicit_default";
  matched_policy_id?: string | null;
  matched_policy_scope?: "global" | "agent" | "skill" | "account" | null;
  default_mode?: "auto" | "notify" | "confirm" | null;
  reason?: string | null;
  precedence: string[];
  note?: string | null;
};

export type AdvisorPolicyPreview = {
  preview_type: "skill_execution_policy_review";
  target_scope: string;
  target_label: string;
  current_effective_mode: "auto" | "notify" | "confirm";
  current_default_execution_policy?: "auto" | "notify" | "confirm" | null;
  suggested_mode?: "auto" | "notify" | "confirm" | null;
  matched_policy_id?: string | null;
  policy_source?: "enforced_policy" | "skill_default" | "implicit_default" | null;
  precedence?: string[];
  reason?: string | null;
  suggested_change?: string | null;
};

export type AdvisorSuggestion = {
  suggestion_id: string;
  suggestion_type:
    | "recovery_suggestion"
    | "failure_pattern"
    | "best_practice_candidate"
    | "policy_draft_suggestion";
  target_type: "platform" | "task" | "run" | "skill" | "policy" | "agent" | "bridge" | "watchdog";
  target_id: string;
  issue_class?: string | null;
  pattern_key?: string | null;
  title: string;
  summary: string;
  rationale: string;
  recommended_action: string;
  evidence_refs: Array<Record<string, unknown>>;
  status: "open" | "accepted" | "dismissed" | "expired";
  severity: "info" | "warning" | "critical";
  confidence?: "low" | "medium" | "high" | null;
  requires_confirmation: boolean;
  occurrence_count?: number | null;
  affected_targets?: number | null;
  last_seen_at?: string | null;
  policy_preview?: AdvisorPolicyPreview | null;
  created_at: string;
  updated_at?: string | null;
  correlation_id?: string | null;
  source_task_id?: string | null;
  source_run_id?: string | null;
  source_watchdog_event_id?: string | null;
  // P2-C: acceptance path hints
  next_action_hint?: string | null;
  next_action_url?: string | null;
};

// ── P3 Governor ──────────────────────────────────────────────────────────────

export type GovernableAction = {
  action_id: string;
  suggestion_id: string;
  action_type: "retry_run" | "acknowledge_escalation" | "resolve_escalation" | "adjust_queue_priority";
  target_type: string;
  target_id: string;
  parameters: Record<string, unknown>;
  risk_level: "low" | "medium" | "high";
  idempotency_key: string;
  created_at: string;
  correlation_id?: string | null;
};

export type GovernorDecision = {
  decision_id: string;
  action_id: string;
  suggestion_id: string;
  decision: "auto_execute" | "require_confirmation" | "deny";
  reason: string;
  policy_snapshot: Record<string, unknown>;
  risk_level: "low" | "medium" | "high";
  gates_passed: string[];
  gates_failed: string[];
  status: "pending" | "confirmed" | "executed" | "denied" | "failed";
  created_at: string;
  executed_at?: string | null;
  confirmed_by?: string | null;
  correlation_id?: string | null;
  source_task_id?: string | null;
  source_watchdog_event_id?: string | null;
};

export type ExecutionReceipt = {
  receipt_id: string;
  decision_id: string;
  action_id: string;
  suggestion_id: string;
  action_type: string;
  target_id: string;
  outcome: "succeeded" | "failed" | "skipped_duplicate";
  error?: string | null;
  result_summary?: string | null;
  executed_at: string;
  idempotency_key: string;
  correlation_id?: string | null;
};

export type GovernorSummary = {
  generated_at: string;
  governor_enabled: boolean;
  auto_execute_enabled: boolean;
  totals: {
    total: number;
    pending: number;
    executed: number;
    denied: number;
    failed: number;
    auto_executed: number;
    confirmed: number;
  };
  pending_decisions: GovernorDecision[];
  recent_receipts: ExecutionReceipt[];
  circuit_breaker_state: Record<string, number>;
};

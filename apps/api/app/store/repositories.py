from __future__ import annotations

from pathlib import Path

from ..models import (
    Account,
    Agent,
    AggregatorDecision,
    AdvisorSuggestion,
    Conversation,
    ConversationMessage,
    Credential,
    ExecutionPolicy,
    ExecutionPlan,
    ExecutionReceipt,
    FileArtifact,
    GovernableAction,
    GovernorDecision,
    LocalBridgeAgentState,
    TaskApproval,
    ActiveMemorySnapshot,
    MemoryCompilerCandidate,
    MemoryCompilerRun,
    MemoryEvent,
    MemoryIndexEntry,
    MemoryItem,
    NotificationChannel,
    NotificationDelivery,
    OrchestratorMasterTask,
    ProcessedActionReceipt,
    AgentApiBinding,
    AgentApiProfile,
    Report,
    RepairAttempt,
    Run,
    RunLogLine,
    RunStep,
    ReferenceCandidate,
    Skill,
    TaskAssignment,
    Task,
    TaskEventRecord,
    VerifierResult,
    WatchdogEvent,
)
from ..settings_env import get_api_data_dir, get_persistence_backend
from .db_store import DbStore
from .file_store import FileStore


DATA_DIR = get_api_data_dir()

_BACKEND = get_persistence_backend()
_IS_DB = _BACKEND == "postgres"


def _store(entity_type: str, model, id_field: str):
    if _IS_DB:
        return DbStore(entity_type, model, id_field)
    return FileStore(DATA_DIR / f"{entity_type}.json", model, id_field)


agents_repo = _store("agents", Agent, "agent_id")
tasks_repo = _store("tasks", Task, "task_id")
conversations_repo = _store("conversations", Conversation, "conversation_id")
conversation_messages_repo = _store("conversation_messages", ConversationMessage, "message_id")
skills_repo = _store("skills", Skill, "skill_id")
accounts_repo = _store("accounts", Account, "account_id")
credentials_repo = _store("credentials", Credential, "credential_id")
memory_repo = _store("memory", MemoryItem, "memory_id")
memory_events_repo = _store("memory_events", MemoryEvent, "event_id")
memory_index_repo = _store("memory_index", MemoryIndexEntry, "index_id")
active_memory_snapshots_repo = _store("active_memory_snapshots", ActiveMemorySnapshot, "snapshot_id")
memory_compiler_runs_repo = _store("memory_compiler_runs", MemoryCompilerRun, "compiler_run_id")
memory_compiler_candidates_repo = _store(
    "memory_compiler_candidates",
    MemoryCompilerCandidate,
    "candidate_id",
)
policies_repo = _store("policies", ExecutionPolicy, "policy_id")
reports_repo = _store("reports", Report, "report_id")
advisor_suggestions_repo = _store("advisor_suggestions", AdvisorSuggestion, "suggestion_id")

task_events_repo = _store("task_events", TaskEventRecord, "event_id")
task_assignments_repo = _store("task_assignments", TaskAssignment, "assignment_id")
runs_repo = _store("runs", Run, "run_id")
run_logs_repo = _store("run_logs", RunLogLine, "log_id")
run_steps_repo = _store("run_steps", RunStep, "run_step_id")
verifier_results_repo = _store("verifier_results", VerifierResult, "result_id")
repair_attempts_repo = _store("repair_attempts", RepairAttempt, "repair_attempt_id")
reference_candidates_repo = _store("reference_candidates", ReferenceCandidate, "candidate_id")
aggregator_decisions_repo = _store("aggregator_decisions", AggregatorDecision, "aggregation_id")
local_bridge_repo = _store("local_bridge", LocalBridgeAgentState, "state_id")
watchdog_events_repo = _store("watchdog_events", WatchdogEvent, "event_id")

approvals_repo = _store("approvals", TaskApproval, "approval_id")
execution_plans_repo = _store("execution_plans", ExecutionPlan, "plan_id")

notification_channels_repo = _store("notification_channels", NotificationChannel, "channel_id")
notification_deliveries_repo = _store("notification_deliveries", NotificationDelivery, "delivery_id")
processed_action_receipts_repo = _store("processed_action_receipts", ProcessedActionReceipt, "receipt_id")

api_profiles_repo = _store("api_profiles", AgentApiProfile, "profile_id")
api_bindings_repo = _store("api_bindings", AgentApiBinding, "binding_id")

file_artifacts_repo = _store("file_artifacts", FileArtifact, "file_id")

# P3 Governor Layer
governable_actions_repo = _store("governable_actions", GovernableAction, "action_id")
governor_decisions_repo = _store("governor_decisions", GovernorDecision, "decision_id")
governor_receipts_repo = _store("governor_receipts", ExecutionReceipt, "receipt_id")

master_tasks_repo = _store("master_tasks", OrchestratorMasterTask, "master_task_id")

from __future__ import annotations

from pathlib import Path

from ..models import (
    Account,
    Agent,
    Conversation,
    ConversationMessage,
    Credential,
    ExecutionPolicy,
    ExecutionPlan,
    FileArtifact,
    LocalBridgeAgentState,
    TaskApproval,
    MemoryItem,
    NotificationChannel,
    NotificationDelivery,
    AgentApiBinding,
    AgentApiProfile,
    Report,
    Run,
    RunLogLine,
    Skill,
    TaskAssignment,
    Task,
    TaskEventRecord,
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
policies_repo = _store("policies", ExecutionPolicy, "policy_id")
reports_repo = _store("reports", Report, "report_id")

task_events_repo = _store("task_events", TaskEventRecord, "event_id")
task_assignments_repo = _store("task_assignments", TaskAssignment, "assignment_id")
runs_repo = _store("runs", Run, "run_id")
run_logs_repo = _store("run_logs", RunLogLine, "log_id")
local_bridge_repo = _store("local_bridge", LocalBridgeAgentState, "state_id")
watchdog_events_repo = _store("watchdog_events", WatchdogEvent, "event_id")

approvals_repo = _store("approvals", TaskApproval, "approval_id")
execution_plans_repo = _store("execution_plans", ExecutionPlan, "plan_id")

notification_channels_repo = _store("notification_channels", NotificationChannel, "channel_id")
notification_deliveries_repo = _store("notification_deliveries", NotificationDelivery, "delivery_id")

api_profiles_repo = _store("api_profiles", AgentApiProfile, "profile_id")
api_bindings_repo = _store("api_bindings", AgentApiBinding, "binding_id")

file_artifacts_repo = _store("file_artifacts", FileArtifact, "file_id")

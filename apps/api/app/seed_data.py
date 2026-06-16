from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Account,
    Agent,
    AgentCapabilities,
    AgentStatus,
    Credential,
    ExecutionPolicy,
    MemoryItem,
    Report,
    Skill,
    Task,
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def seed_agents() -> list[Agent]:
    """Fresh-store default: built-in operator only. Add external agents via POST /agents or the web UI."""
    now = _now_iso()
    return [
        Agent(
            agent_id="octopus_builtin",
            display_name="Kanaloa",
            type="builtin",
            status=AgentStatus.idle,
            adapter_id="builtin_octopus",
            integration_mode="embedded",
            integration_channels=["builtin"],
            control_depth="partial",
            capabilities=AgentCapabilities(
                can_chat=True,
                can_code=False,
                can_browse=False,
                can_use_skills=True,
                supports_structured_task=False,
            ),
            last_heartbeat_at=now,
        ),
    ]


def seed_tasks() -> list[Task]:
    return []


def seed_skills() -> list[Skill]:
    return [
        Skill(
            skill_id="skill_text_summarize",
            name="Text: Summarize",
            version="1.0.0",
            category="text",
            description="Builtin skill: summarize a text payload (no external calls).",
            risk_level="low",
            default_execution_policy="auto",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}, "max_len": {"type": "number"}}},
            output_schema={"type": "object", "properties": {"summary": {"type": "string"}, "max_len": {"type": "number"}}},
        ),
        Skill(
            skill_id="skill_http_request",
            name="HTTP: Request",
            version="1.0.0",
            category="network",
            description="Outbound HTTP request (policy gating recommended). Optional credential_ref for Bearer auth.",
            risk_level="high",
            default_execution_policy="confirm",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string"},
                    "headers": {"type": "object"},
                    "body": {"type": "string"},
                    "timeout_s": {"type": "number"},
                    "credential_ref": {"type": "string"},
                },
                "required": ["url"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status_code": {"type": "number"},
                    "headers": {"type": "object"},
                    "text_excerpt": {"type": "string"},
                },
            },
        ),
        Skill(
            skill_id="skill_connect_agent",
            name="Connect: External Agent",
            version="1.0.0",
            category="platform_onboarding",
            description="Stepwise guide to register an external agent via Local Bridge (HTTP/CLI/handoff/script).",
            risk_level="low",
            default_execution_policy="auto",
            skill_scope="platform",
            input_schema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "string",
                        "enum": ["guide", "probe", "draft", "register", "test_run", "handoff_guide"],
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["http_webhook", "cli_sync", "handoff_only", "local_script"],
                    },
                    "display_name": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "webhook_url": {"type": "string"},
                    "cli_path": {"type": "string"},
                    "shell_command": {"type": "string"},
                    "confirmed": {"type": "boolean"},
                    "register_bridge": {"type": "boolean"},
                },
            },
            output_schema={"type": "object"},
        ),
        Skill(
            skill_id="skill_handoff_guide",
            name="Handoff: Callback Guide",
            version="1.0.0",
            category="platform_onboarding",
            description="Read-only checklist for completing a handoff task via external tool + callback.",
            risk_level="low",
            default_execution_policy="auto",
            skill_scope="platform",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["task_id"],
            },
            output_schema={"type": "object"},
        ),
    ]


def seed_accounts() -> list[Account]:
    return []


def seed_credentials() -> list[Credential]:
    return []


def seed_policies() -> list[ExecutionPolicy]:
    return [
        ExecutionPolicy(
            policy_id="pol_global_default",
            scope="global",
            target_id=None,
            mode="auto",
            note="Default: auto-allow runs; add confirm-scoped policies via /policies if needed.",
            is_draft=False,
        )
    ]


def seed_reports() -> list[Report]:
    return []


def seed_memory() -> list[MemoryItem]:
    return []

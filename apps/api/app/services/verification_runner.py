"""
Verification plans for orchestrator: maps known repo checks to instruction fragments.

Execution never happens here — orchestrator dispatches via kanaloa_actions / worker.
"""

from __future__ import annotations

import re
from typing import Any

# registry key -> human label + instruction snippet for Bridge/local_script or Claude
KNOWN_CHECKS: list[tuple[str, str, str]] = [
    ("npm_test_api", "npm run test:api", "Run API pytest via npm at repo root: npm run test:api"),
    ("npm_build_web", "npm run build:web", "Build web workspace: npm run build:web"),
    ("docker_compose_config", "docker compose config", "Validate compose file: docker compose config"),
    ("pytest", "pytest", "Run pytest in apps/api: cd apps/api && .venv/Scripts/python -m pytest -q"),
    ("npm_test", "npm test", "Run default npm test at repo root"),
    ("npm_lint", "npm run lint", "Run lint if configured: npm run lint"),
]


def detect_verification_commands(user_instruction: str) -> list[dict[str, Any]]:
    """Derive which verification keys apply from natural language + defaults."""
    low = user_instruction.lower()
    keys: list[str] = []
    if "测试" in user_instruction or "test" in low or "pytest" in low:
        keys.extend(["npm_test_api", "pytest"])
    if "build" in low or "构建" in user_instruction:
        keys.append("npm_build_web")
    if "docker" in low or "compose" in low:
        keys.append("docker_compose_config")
    if "lint" in low:
        keys.append("npm_lint")
    # dedupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    if not ordered:
        ordered = ["npm_test_api"]
    out: list[dict[str, Any]] = []
    for key in ordered[:4]:
        row = next((x for x in KNOWN_CHECKS if x[0] == key), None)
        if row:
            out.append({"command_key": row[0], "command": row[1], "instruction": row[2]})
    return out


def build_verification_subtask_specs(user_instruction: str) -> list[dict[str, Any]]:
    """Planner entries merged into orchestrator subtasks (kind=verification)."""
    cmds = detect_verification_commands(user_instruction)
    specs: list[dict[str, Any]] = []
    for i, c in enumerate(cmds):
        specs.append(
            {
                "id": f"verify_{i}_{c['command_key']}",
                "kind": "verification",
                "title": f"Verify: {c['command_key']}",
                "instruction": (
                    f"[KANALOA_VERIFICATION:{c['command_key']}]\n{c['instruction']}\n"
                    f"Context: {user_instruction[:800]}"
                ),
                "command_key": c["command_key"],
            }
        )
    return specs


def verification_record_template(
    *,
    command_key: str | None,
    command: str | None,
    status: str,
    exit_code: int | None,
    output_summary: str | None,
    error_summary: str | None,
    verification_phase: str | None = None,
    platform_task_id: str | None = None,
    platform_task_status: str | None = None,
) -> dict[str, Any]:
    return {
        "command": command,
        "command_key": command_key,
        "status": status,
        "exit_code": exit_code,
        "output_summary": output_summary,
        "error_summary": error_summary,
        "verification_phase": verification_phase or status,
        "platform_task_id": platform_task_id,
        "platform_task_status": platform_task_status,
    }

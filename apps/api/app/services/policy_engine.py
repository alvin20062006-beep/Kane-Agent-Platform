from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Agent, ExecutionPolicy, Task
from ..store.repositories import policies_repo


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _policy_override_active(task: Task) -> bool:
    payload = task.result_payload or {}
    until = payload.get("policy_override_until")
    if not until or not isinstance(until, str):
        return False
    try:
        return _parse_iso(until) > _now()
    except Exception:
        return False


class PolicyDecision:
    def __init__(self, *, allow: bool, require_approval: bool, reason: str | None, policy: ExecutionPolicy | None):
        self.allow = allow
        self.require_approval = require_approval
        self.reason = reason
        self.policy = policy


def evaluate_task_run(task: Task, agent: Agent) -> PolicyDecision:
    """
    Beta policy evaluation (minimal, stable, non-breaking defaults):

    - Only policies with is_mock == False are enforced (opt-in).
    - If a policy override is active on the task (recent approval), do not re-gate.
    - Scope resolution order (first match wins): agent -> global.
    """
    if _policy_override_active(task):
        return PolicyDecision(allow=True, require_approval=False, reason="policy_override_active", policy=None)

    policies = [p for p in policies_repo.list() if not getattr(p, "is_mock", True)]
    if not policies:
        return PolicyDecision(allow=True, require_approval=False, reason=None, policy=None)

    chosen: ExecutionPolicy | None = None
    for p in policies:
        if p.scope == "agent" and p.target_id == agent.agent_id:
            chosen = p
            break
    if not chosen:
        chosen = next((p for p in policies if p.scope == "global"), None)

    if not chosen:
        return PolicyDecision(allow=True, require_approval=False, reason=None, policy=None)

    if chosen.mode == "auto":
        return PolicyDecision(allow=True, require_approval=False, reason=None, policy=chosen)
    if chosen.mode == "notify":
        return PolicyDecision(allow=True, require_approval=False, reason="notify_only", policy=chosen)
    if chosen.mode == "confirm":
        return PolicyDecision(
            allow=True,
            require_approval=True,
            reason=f"policy_confirm_required ({chosen.policy_id})",
            policy=chosen,
        )

    return PolicyDecision(allow=True, require_approval=False, reason=None, policy=chosen)


def build_policy_override_until(minutes: int = 5) -> str:
    return (_now() + timedelta(minutes=minutes)).isoformat()


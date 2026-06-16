from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Agent, ExecutionPolicy, PolicyExplanation, Skill, Task
from ..store.repositories import policies_repo, skills_repo


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
    Policy evaluation (minimal, stable, non-breaking defaults):

    - Only policies with is_draft == False are enforced (opt-in).
    - If a policy override is active on the task (recent approval), do not re-gate.
    - Scope resolution order (first match wins): agent -> global.
    """
    if _policy_override_active(task):
        return PolicyDecision(allow=True, require_approval=False, reason="policy_override_active", policy=None)

    policies = [p for p in policies_repo.list() if not getattr(p, "is_draft", True)]
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


def _enforced_policies() -> list[ExecutionPolicy]:
    return [p for p in policies_repo.list() if not getattr(p, "is_draft", True)]


def _find_policy(scope: str, target_id: str | None, policies: list[ExecutionPolicy]) -> ExecutionPolicy | None:
    if scope == "global":
        return next((p for p in policies if p.scope == "global"), None)
    return next((p for p in policies if p.scope == scope and p.target_id == target_id), None)


def build_policy_explanation(scope: str, target_id: str | None = None) -> PolicyExplanation:
    if scope not in {"global", "agent", "skill", "account"}:
        scope = "global"
        target_id = None

    enforced = _enforced_policies()
    global_policy = _find_policy("global", None, enforced)
    direct_policy = _find_policy(scope, target_id, enforced) if scope != "global" else global_policy

    if direct_policy:
        return PolicyExplanation(
            scope=scope,  # type: ignore[arg-type]
            target_id=target_id,
            effective_mode=direct_policy.mode,
            policy_source="enforced_policy",
            matched_policy_id=direct_policy.policy_id,
            matched_policy_scope=direct_policy.scope,
            reason=f"Matched enforced {direct_policy.scope} policy {direct_policy.policy_id}",
            precedence=[scope, "global"] if scope != "global" else ["global"],
            note=direct_policy.note,
        )

    if scope == "skill" and target_id:
        skill = skills_repo.get(target_id)
        if skill:
            return PolicyExplanation(
                scope="skill",
                target_id=target_id,
                effective_mode=skill.default_execution_policy,
                policy_source="skill_default",
                default_mode=skill.default_execution_policy,
                reason=f"No skill override matched; using skill default_execution_policy from {skill.skill_id}",
                precedence=["skill", "skill_default", "global"],
                note=skill.description,
            )

    if scope != "global" and global_policy:
        return PolicyExplanation(
            scope=scope,  # type: ignore[arg-type]
            target_id=target_id,
            effective_mode=global_policy.mode,
            policy_source="enforced_policy",
            matched_policy_id=global_policy.policy_id,
            matched_policy_scope=global_policy.scope,
            reason=f"No {scope} override matched; using enforced global policy {global_policy.policy_id}",
            precedence=[scope, "global"],
            note=global_policy.note,
        )

    return PolicyExplanation(
        scope=scope,  # type: ignore[arg-type]
        target_id=target_id,
        effective_mode="auto",
        policy_source="implicit_default",
        reason="No enforced policy matched; falling back to implicit auto behavior",
        precedence=[scope, "global"] if scope != "global" else ["global"],
    )


def explain_skill_execution(skill: Skill) -> PolicyExplanation:
    return build_policy_explanation("skill", skill.skill_id)


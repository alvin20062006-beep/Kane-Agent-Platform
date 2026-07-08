from __future__ import annotations

from typing import Literal

from ..models import Run, RunStep
from ..store.repositories import run_steps_repo, runs_repo
from ..store.run_step_queries import list_steps_for_run
from .runtime_audit import now_iso

StepType = Literal["plan", "execute", "summarize"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "blocked", "skipped"]

_BASE_STEPS: tuple[tuple[StepType, int, str], ...] = (
    ("plan", 1, "Plan execution attempt"),
    ("execute", 2, "Execute attempt"),
    ("summarize", 3, "Summarize attempt outcome"),
)


def _step_id(run_id: str, step_type: StepType) -> str:
    return f"{run_id}_step_{step_type}"


def ensure_base_run_steps(run: Run) -> list[RunStep]:
    existing, _total = list_steps_for_run(run.run_id)
    by_type = {step.step_type: step for step in existing}
    created_at = now_iso()
    out = list(existing)
    for step_type, sequence, title in _BASE_STEPS:
        if step_type in by_type:
            continue
        step = RunStep(
            run_step_id=_step_id(run.run_id, step_type),
            run_id=run.run_id,
            task_id=run.task_id,
            sequence=sequence,
            step_type=step_type,
            status="succeeded" if step_type == "plan" else "pending",
            title=title,
            agent_id=run.agent_id,
            input_context_ref=f"run:{run.run_id}:input_snapshot" if step_type == "plan" else None,
            created_at=created_at,
            updated_at=created_at,
            started_at=created_at if step_type == "plan" else None,
            completed_at=created_at if step_type == "plan" else None,
            correlation_id=run.correlation_id,
        )
        run_steps_repo.upsert(step)
        out.append(step)
    out.sort(key=lambda x: (x.sequence, x.created_at, x.run_step_id))
    return out


def mark_run_step(
    run_id: str,
    step_type: StepType,
    status: StepStatus,
    *,
    agent_id: str | None = None,
    output_ref: str | None = None,
    failure_id: str | None = None,
) -> RunStep | None:
    run = runs_repo.get(run_id)
    if not run:
        return None
    ensure_base_run_steps(run)
    step = run_steps_repo.get(_step_id(run_id, step_type))
    if not step:
        return None
    ts = now_iso()
    update: dict[str, object] = {"status": status, "updated_at": ts}
    if status == "running" and not step.started_at:
        update["started_at"] = ts
    if status in {"succeeded", "failed", "blocked", "skipped"}:
        update["completed_at"] = ts
        if not step.started_at:
            update["started_at"] = ts
    if agent_id:
        update["agent_id"] = agent_id
    if output_ref:
        update["output_ref"] = output_ref
    if failure_id:
        update["failure_id"] = failure_id
    updated = step.model_copy(update=update)
    return run_steps_repo.upsert(updated)


def complete_run_timeline(run_id: str, *, succeeded: bool) -> None:
    status: StepStatus = "succeeded" if succeeded else "failed"
    failure_id = None if succeeded else f"run:{run_id}:error"
    mark_run_step(
        run_id,
        "execute",
        status,
        output_ref=f"run:{run_id}:output_snapshot",
        failure_id=failure_id,
    )
    mark_run_step(
        run_id,
        "summarize",
        "succeeded",
        output_ref=f"run:{run_id}:output_snapshot",
        failure_id=failure_id,
    )

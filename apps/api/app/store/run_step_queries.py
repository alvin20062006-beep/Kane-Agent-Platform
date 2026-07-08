"""Filtered RunStep reads for the execution timeline."""

from __future__ import annotations

from ..models import RunStep
from .repositories import run_steps_repo


def list_steps_for_run(run_id: str) -> tuple[list[RunStep], int]:
    steps = [step for step in run_steps_repo.list() if step.run_id == run_id]
    steps.sort(key=lambda x: (x.sequence, x.created_at, x.run_step_id))
    return steps, len(steps)

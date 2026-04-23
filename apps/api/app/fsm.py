"""Task state machine (vendored from packages/core for Beta; keep in sync)."""

from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    created = "created"
    queued = "queued"
    assigned = "assigned"
    running = "running"
    waiting_approval = "waiting_approval"
    stalled = "stalled"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class TaskEvent(str, Enum):
    task_created = "task_created"
    queued = "queued"
    agent_assigned = "agent_assigned"
    run_started = "run_started"
    approval_requested = "approval_requested"
    task_stalled = "task_stalled"
    task_succeeded = "task_succeeded"
    task_failed = "task_failed"
    task_cancelled = "task_cancelled"
    task_expired = "task_expired"
    retry_requested = "retry_requested"


_TRANSITIONS: dict[TaskState, dict[TaskEvent, TaskState]] = {
    TaskState.created: {
        TaskEvent.queued: TaskState.queued,
        TaskEvent.agent_assigned: TaskState.assigned,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.queued: {
        TaskEvent.agent_assigned: TaskState.assigned,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.assigned: {
        TaskEvent.run_started: TaskState.running,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.running: {
        TaskEvent.approval_requested: TaskState.waiting_approval,
        TaskEvent.task_stalled: TaskState.stalled,
        TaskEvent.task_succeeded: TaskState.succeeded,
        TaskEvent.task_failed: TaskState.failed,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.waiting_approval: {
        TaskEvent.run_started: TaskState.running,
        TaskEvent.retry_requested: TaskState.assigned,
        TaskEvent.task_succeeded: TaskState.succeeded,
        TaskEvent.task_failed: TaskState.failed,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.stalled: {
        TaskEvent.run_started: TaskState.running,
        TaskEvent.task_failed: TaskState.failed,
        TaskEvent.task_cancelled: TaskState.cancelled,
        TaskEvent.task_expired: TaskState.expired,
    },
    TaskState.succeeded: {},
    TaskState.failed: {
        TaskEvent.retry_requested: TaskState.assigned,
        TaskEvent.task_cancelled: TaskState.cancelled,
    },
    TaskState.cancelled: {},
    TaskState.expired: {},
}


def can_transition(state: TaskState, event: TaskEvent) -> bool:
    return event in _TRANSITIONS.get(state, {})


def transition(state: TaskState, event: TaskEvent) -> TaskState:
    if not can_transition(state, event):
        raise ValueError(f"Invalid transition: {state} --{event}--> ?")
    return _TRANSITIONS[state][event]

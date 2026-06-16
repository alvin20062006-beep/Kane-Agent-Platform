"""Task FSM — single source: packages/core/octopus_core/state_machine/task.py"""

from __future__ import annotations

import sys
from pathlib import Path

_core = Path(__file__).resolve().parents[3] / "packages" / "core"
if str(_core) not in sys.path:
    sys.path.insert(0, str(_core))

from octopus_core.state_machine.task import (  # noqa: E402
    TaskEvent,
    TaskState,
    can_transition,
    transition,
)

apply_event = transition

__all__ = ["TaskState", "TaskEvent", "apply_event", "can_transition", "transition"]

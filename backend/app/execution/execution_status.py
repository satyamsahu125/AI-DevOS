from __future__ import annotations

from enum import Enum


class ExecutionStatus(str, Enum):
    Idle = "idle"
    Ready = "ready"
    Running = "running"
    Completed = "completed"
    Failed = "failed"

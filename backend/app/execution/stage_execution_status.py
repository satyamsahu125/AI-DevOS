from __future__ import annotations

from enum import Enum


class StageExecutionStatus(str, Enum):
    Completed = "completed"
    Failed = "failed"

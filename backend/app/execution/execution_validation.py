from __future__ import annotations

from .execution_status import ExecutionStatus


class ExecutionValidation:
    """Validates the execution engine lifecycle state."""

    def validate(self, status: ExecutionStatus) -> None:
        if status not in {ExecutionStatus.Ready, ExecutionStatus.Running, ExecutionStatus.Completed, ExecutionStatus.Failed}:
            raise ValueError("invalid execution status")

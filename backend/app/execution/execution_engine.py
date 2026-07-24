from __future__ import annotations

from typing import Any

from ..artifact.manager import ArtifactManager
from ..context.context import AgentContext
from ..workflow.transition_manager import TransitionManager
from .execution_metrics import ExecutionMetrics
from .execution_result import ExecutionResult
from .execution_status import ExecutionStatus
from .execution_validation import ExecutionValidation
from .stage_executor import StageExecutor


class ExecutionEngine:
    """Coordinates workflow-stage execution and delegates to the stage executor."""

    def __init__(self, artifact_manager: ArtifactManager | None = None, transition_manager: TransitionManager | None = None, validation: ExecutionValidation | None = None) -> None:
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.transition_manager = transition_manager or TransitionManager()
        self.validation = validation or ExecutionValidation()
        self.stage_executor = StageExecutor(artifact_manager=self.artifact_manager)
        self.metrics = ExecutionMetrics()
        self.status = ExecutionStatus.Idle

    def initialize(self) -> None:
        self.status = ExecutionStatus.Ready

    def execute(self, stage_name: str, content: str) -> ExecutionResult:
        self.status = ExecutionStatus.Running
        result = self.stage_executor.execute(stage_name, content)
        self.status = ExecutionStatus.Completed if result.success else ExecutionStatus.Failed
        return ExecutionResult(
            success=result.success,
            artifact=result.artifact,
            error=result.error,
            execution_time=result.execution_time,
            metadata={"stage_name": stage_name, "status": self.status.value},
        )

    def execute_stage(self, stage_name: str, content: str) -> ExecutionResult:
        return self.execute(stage_name, content)

    def execute_reviewer(self, stage_name: str, content: str) -> ExecutionResult:
        return self.execute(stage_name, content)

    def resume(self) -> None:
        self.status = ExecutionStatus.Ready

    def rollback(self) -> None:
        self.status = ExecutionStatus.Idle

    def shutdown(self) -> None:
        self.status = ExecutionStatus.Idle

    def status(self) -> ExecutionStatus:
        return self.status

    def validate(self) -> None:
        self.validation.validate(self.status)

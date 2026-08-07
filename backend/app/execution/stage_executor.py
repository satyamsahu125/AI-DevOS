from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..runtime.agent_runtime import AgentRuntime
from .stage_execution_result import StageExecutionResult
from .stage_execution_status import StageExecutionStatus
from .stage_validation import StageValidation


class StageExecutor:
    """Executes exactly one workflow stage using the agent runtime."""

    def __init__(self, artifact_manager: ArtifactManager | None = None, runtime: AgentRuntime | None = None, validation: StageValidation | None = None) -> None:
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.runtime = runtime or AgentRuntime()
        self.validation = validation or StageValidation()

    def execute(self, stage_name: str, content: str) -> StageExecutionResult:
        artifact = self.runtime.execute(stage_name, content).artifact
        self.validation.validate(artifact)
        return StageExecutionResult(
            stage=stage_name,
            agent=stage_name,
            artifact=artifact,
            status=StageExecutionStatus.Completed,
            execution_time=0.0,
            errors=[],
        )

    def resolve_agent(self, stage_name: str) -> object:
        return self.runtime.resolve(stage_name)

    def validate_result(self, result: StageExecutionResult) -> None:
        self.validation.validate(result.artifact)

    def cleanup(self) -> None:
        return None

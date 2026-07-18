from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from .pipeline import ExecutionPipeline
from .execution_result import ExecutionResult as DocumentedExecutionResult


class ExecutionEngine:
    def __init__(self, artifact_manager: ArtifactManager | None = None) -> None:
        self.pipeline = ExecutionPipeline(artifact_manager)

    def execute(self, stage_name: str, content: str) -> ExecutionResult:
        result = self.pipeline.run(stage_name, content)
        return DocumentedExecutionResult(
            success=result.success,
            artifact=result.artifact,
            error=None,
            execution_time=0.0,
            metadata={"stage_name": stage_name},
        )

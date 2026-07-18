from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from ..shared.models.stage_artifact import StageArtifact


class ExecutionPipeline:
    def __init__(self, artifact_manager: ArtifactManager | None = None) -> None:
        self.artifact_manager = artifact_manager or ArtifactManager()

    def run(self, stage_name: str, content: str) -> ExecutionResult:
        artifact = StageArtifact(
            artifact_id="",
            name=stage_name,
            content=content,
            status="Generated",
        )
        stored = self.artifact_manager.save_artifact(artifact)
        return ExecutionResult(artifact=stored, success=True, message="completed")

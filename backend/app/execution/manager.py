from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from .engine import ExecutionEngine


class ExecutionManager:
    def __init__(self, artifact_manager: ArtifactManager | None = None) -> None:
        self.engine = ExecutionEngine(artifact_manager)

    def execute_stage(self, stage_name: str, content: str) -> ExecutionResult:
        return self.engine.execute(stage_name, content)

from __future__ import annotations

import logging

from ..agents.factory import AgentFactory
from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from .pipeline import ExecutionPipeline
from .execution_result import ExecutionResult as DocumentedExecutionResult
from .safety_policy import SafetyPolicy

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Coordinates execution of exactly one workflow stage via ExecutionPipeline.

    Owns the SafetyPolicy that ExecutionPipeline checks before every write
    (see safety_policy.py, inspired by gstack's /careful skill).
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager | None = None,
        agent_factory: AgentFactory | None = None,
        safety_policy: SafetyPolicy | None = None,
    ) -> None:
        """Wire the pipeline (and its SafetyPolicy) used to execute a single stage.

        When safety_policy isn't given explicitly, it's rooted at the artifact manager's own
        WorkspaceManager root (see ExecutionPipeline's docstring for why a bare SafetyPolicy()
        default is unsafe once new-file writes are checked against the workspace boundary).
        """
        artifact_manager = artifact_manager or ArtifactManager()
        self.safety_policy = safety_policy or SafetyPolicy(workspace_root=artifact_manager.workspace_manager.root)
        self.pipeline = ExecutionPipeline(artifact_manager, agent_factory, safety_policy=self.safety_policy)

    def execute(self, project_id: str, stage_name: str, content: str, attempt: int = 1) -> ExecutionResult:
        """Execute stage_name via the pipeline (scoped to project_id) and return a normalized ExecutionResult."""
        logger.info("execution engine executing: project_id=%s stage=%s attempt=%s", project_id, stage_name, attempt)
        result = self.pipeline.run(project_id, stage_name, content, attempt=attempt)
        return DocumentedExecutionResult(
            success=result.success,
            artifact=result.artifact,
            error=None,
            execution_time=0.0,
            metadata={"stage_name": stage_name},
        )

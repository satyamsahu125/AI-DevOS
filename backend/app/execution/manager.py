from __future__ import annotations

import logging

from ..agents.factory import AgentFactory
from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from .engine import ExecutionEngine

logger = logging.getLogger(__name__)


class ExecutionManager:
    """Public entry point for executing a single workflow stage."""

    def __init__(
        self,
        artifact_manager: ArtifactManager | None = None,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        """Wire the execution engine used to run a stage."""
        self.engine = ExecutionEngine(artifact_manager, agent_factory)

    def execute_stage(self, project_id: str, stage_name: str, content: str, attempt: int = 1) -> ExecutionResult:
        """Execute stage_name with content (scoped to project_id) and return the resulting ExecutionResult."""
        logger.info("execution manager executing: project_id=%s stage=%s attempt=%s", project_id, stage_name, attempt)
        return self.engine.execute(project_id, stage_name, content, attempt=attempt)

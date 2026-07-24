from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

from ..agents.factory import AgentFactory
from ..artifact.manager import ArtifactManager
from ..shared.dto.execution_result import ExecutionResult
from ..shared.enums.stage import Stage
from .safety_policy import OperationType, SafetyDecision, SafetyException, SafetyPolicy

logger = logging.getLogger(__name__)


class ExecutionPipeline:
    """Executes exactly one workflow stage by resolving and running its agent.

    Resolves stage_name to a concrete agent via AgentFactory, executes it
    with content as the agent's input context, and persists the resulting
    artifact through ArtifactManager -- after checking the write against
    SafetyPolicy (see safety_policy.py, inspired by gstack's /careful skill).
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager | None = None,
        agent_factory: AgentFactory | None = None,
        safety_policy: SafetyPolicy | None = None,
    ) -> None:
        """Wire the artifact manager, agent factory, and safety policy used to run a stage.

        When safety_policy isn't given explicitly, it's rooted at the artifact manager's own
        WorkspaceManager root rather than SafetyPolicy's bare default -- otherwise an isolated
        ArtifactManager (e.g. one rooted at a temp dir in tests) would have every one of its
        writes classified as "outside the workspace" now that new-file writes are correctly
        checked against the workspace boundary too (see safety_policy.py).
        """
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.agent_factory = agent_factory or AgentFactory()
        self.safety_policy = safety_policy or SafetyPolicy(workspace_root=self.artifact_manager.workspace_manager.root)

    def run(self, project_id: str, stage_name: str, content: str, attempt: int = 1) -> ExecutionResult:
        """Execute stage_name's agent against content, safety-check the write, then persist the artifact
        under project_id's workspace (attempt is 1-indexed and preserved as artifact history)."""
        logger.info("execution pipeline running: project_id=%s stage=%s attempt=%s", project_id, stage_name, attempt)
        agent = self.agent_factory.create(stage_name)
        artifact = agent.execute(SimpleNamespace(content=content, project_id=project_id))
        if not artifact.artifact_id:
            artifact.artifact_id = str(uuid4())

        stage = Stage(stage_name)
        target_path = self.artifact_manager.workspace_manager.get_artifact_path(project_id, stage.value)
        decision = self.safety_policy.check(OperationType.FILE_OVERWRITE, str(target_path), attempt=attempt)
        if decision.decision == SafetyDecision.BLOCK:
            logger.error("execution pipeline blocked: stage=%s reason=%s", stage_name, decision.reason)
            raise SafetyException(decision.reason)
        if decision.decision == SafetyDecision.WARN:
            logger.warning("execution pipeline warning: stage=%s reason=%s", stage_name, decision.reason)
            artifact.safety_flags.append(decision.reason)

        stored = self.artifact_manager.save_artifact(
            project_id=project_id,
            stage=stage,
            content=artifact.content,
            structured_content=artifact.structured_content,
            attempt=attempt,
            artifact_id=artifact.artifact_id,
            schema_type=artifact.schema_type,
            safety_flags=artifact.safety_flags,
        )
        logger.info("execution pipeline completed: stage=%s artifact_id=%s", stage_name, stored.artifact_id)
        return ExecutionResult(artifact=stored, success=True, message="completed")

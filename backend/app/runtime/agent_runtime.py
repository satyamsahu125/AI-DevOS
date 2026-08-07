from __future__ import annotations

from ..agents.base_agent import BaseAgent
from ..artifact.manager import ArtifactManager
from ..context.context import AgentContext
from ..shared.models.stage_artifact import StageArtifact
from .agent_factory import AgentFactory
from .runtime_validation import RuntimeValidation


class AgentRuntime:
    """Resolves, creates, executes, and disposes agents for a stage."""

    def __init__(self, factory: AgentFactory | None = None, validator: RuntimeValidation | None = None) -> None:
        self.factory = factory or AgentFactory()
        self.validator = validator or RuntimeValidation()
        self.artifact_manager = ArtifactManager()

    def initialize(self) -> None:
        self.validator.validate(self.factory)

    def resolve(self, stage_name: str) -> BaseAgent:
        return self.factory.create(stage_name)

    def create(self, stage_name: str) -> BaseAgent:
        return self.resolve(stage_name)

    def execute(self, stage_name: str, content: str) -> StageArtifact:
        agent = self.create(stage_name)
        context = AgentContext(project_name="demo", requirements=content, architecture="runtime")
        artifact = agent.execute(context)
        self.validator.validate(artifact)
        return artifact

    def dispose(self, agent: BaseAgent) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def validate(self) -> None:
        self.validator.validate(self.factory)

    def status(self) -> str:
        return "ready"

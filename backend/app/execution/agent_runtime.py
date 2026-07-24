from __future__ import annotations

from ..shared.models.stage_artifact import StageArtifact
from .runtime_context import RuntimeContext
from .runtime_result import RuntimeResult
from .runtime_validation import RuntimeValidator
from ..agents.factory import AgentFactory


class AgentRuntime:
    """Executes a single stage through the documented agent factory."""

    def __init__(self, factory: AgentFactory | None = None, validator: RuntimeValidator | None = None) -> None:
        self.factory = factory or AgentFactory()
        self.validator = validator or RuntimeValidator()

    def execute(self, stage_name: str, content: str) -> RuntimeResult:
        context = RuntimeContext(stage_name=stage_name, content=content)
        agent = self.factory.create(stage_name)
        artifact = agent.execute(context)
        self.validator.validate(artifact)
        return RuntimeResult(artifact=artifact, success=True, message="stage executed")

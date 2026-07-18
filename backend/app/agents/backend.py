from __future__ import annotations

from ..prompt.backend_builder import BackendPromptBuilder
from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent


class BackendDeveloperAgent(BaseAgent):
    """Minimal backend agent implementation for the documented runtime."""

    def __init__(self, prompt_builder: BackendPromptBuilder | None = None) -> None:
        self.prompt_builder = prompt_builder or BackendPromptBuilder()

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "") if context is not None else ""
        prompt = self.prompt_builder.build(content)
        return StageArtifact(artifact_id="", name="backend", content=prompt, status="Generated")

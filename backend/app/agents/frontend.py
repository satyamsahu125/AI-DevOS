from __future__ import annotations

from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent


class FrontendDeveloperAgent(BaseAgent):
    """Minimal frontend agent implementation for the documented runtime."""

    def execute(self, context: object) -> StageArtifact:
        return StageArtifact(artifact_id="", name="frontend", content=str(context), status="Generated")

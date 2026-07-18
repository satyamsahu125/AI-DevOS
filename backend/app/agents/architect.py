from __future__ import annotations

from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent


class ArchitectAgent(BaseAgent):
    """Minimal architect agent that matches the later documented contract."""

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "") if context is not None else ""
        return StageArtifact(artifact_id="", name="architecture", content=str(content), status="Generated")

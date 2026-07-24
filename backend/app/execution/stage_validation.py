from __future__ import annotations

from ..shared.models.stage_artifact import StageArtifact


class StageValidation:
    """Validates that a stage produced a usable artifact."""

    def validate(self, artifact: StageArtifact | None) -> None:
        if artifact is None:
            raise ValueError("artifact is required")
        if not artifact.content:
            raise ValueError("artifact content is empty")

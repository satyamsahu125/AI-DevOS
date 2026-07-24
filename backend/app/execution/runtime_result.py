from __future__ import annotations

from dataclasses import dataclass

from ..shared.models.stage_artifact import StageArtifact


@dataclass(slots=True)
class RuntimeResult:
    """Result returned by the execution runtime."""

    artifact: StageArtifact
    success: bool
    message: str = ""

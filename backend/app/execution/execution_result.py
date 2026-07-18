from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..shared.models.stage_artifact import StageArtifact


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    artifact: StageArtifact
    error: str | None = None
    execution_time: float = 0.0
    metadata: dict[str, Any] | None = None

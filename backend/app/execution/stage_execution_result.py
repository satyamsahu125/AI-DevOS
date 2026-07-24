from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..shared.models.stage_artifact import StageArtifact
from .stage_execution_status import StageExecutionStatus


@dataclass(slots=True)
class StageExecutionResult:
    stage: str
    agent: str
    artifact: StageArtifact | None = None
    status: StageExecutionStatus = StageExecutionStatus.Completed
    execution_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

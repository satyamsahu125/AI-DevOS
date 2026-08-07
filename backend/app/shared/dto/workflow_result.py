from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models.workflow import Workflow


@dataclass(slots=True)
class WorkflowResult:
    workflow: Workflow
    success: bool
    message: str
    stopped: bool = False
    # BUG-3 fix: artifact carries the approved StageArtifact object so
    # PipelineSupervisor can inspect structured_content for BugAnalyst rollback logic.
    artifact: Any = field(default=None)

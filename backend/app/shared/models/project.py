from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..enums.project_state import ProjectState
from ..enums.stage import Stage


@dataclass
class Project:
    project_id: str
    name: str
    description: str
    workspace_path: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_stage: Stage = Stage.ProductOwner
    status: str = "active"
    # Lifecycle state. A freshly created project has run nothing yet, so it
    # starts EMPTY -- current_stage above is only the stage the pipeline would
    # run next, not evidence that anything has executed.
    state: ProjectState = ProjectState.EMPTY

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..enums.stage import Stage


@dataclass
class Project:
    project_id: str
    name: str
    description: str
    workspace_path: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    current_stage: Stage = Stage.ProductOwner

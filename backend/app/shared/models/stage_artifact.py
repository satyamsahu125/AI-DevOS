from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..enums.artifact_status import ArtifactStatus
from ..enums.artifact_type import ArtifactType


@dataclass
class StageArtifact:
    artifact_id: str
    name: str
    content: str
    status: ArtifactStatus = ArtifactStatus.Draft
    artifact_type: ArtifactType = ArtifactType.Requirements
    created_at: datetime = field(default_factory=datetime.utcnow)
    location: Optional[Path] = None

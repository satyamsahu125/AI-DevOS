from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..enums.artifact_status import ArtifactStatus
from ..enums.artifact_type import ArtifactType


@dataclass
class StageArtifact:
    artifact_id: str
    name: str
    content: str
    status: ArtifactStatus = ArtifactStatus.Draft
    artifact_type: ArtifactType = ArtifactType.Requirements
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    location: Optional[Path] = None
    schema_type: str = ""
    structured_content: dict[str, Any] = field(default_factory=dict)
    safety_flags: list[str] = field(default_factory=list)
    project_id: str = ""
    attempt: int = 1

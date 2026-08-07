from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class ArchitectureArtifact:
    artifact_id: str
    name: str
    version: int
    status: str
    created_at: Optional[datetime]
    approved_at: Optional[datetime]
    location: Optional[Path]
    content: str
    author: str
    reviewer: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)

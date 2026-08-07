from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RecoveryCheckpoint:
    """Represents a recoverable execution checkpoint."""

    checkpoint_id: str
    workflow_id: str = ""
    project_id: str = ""
    session_id: str = ""
    current_stage: str = ""
    workflow_state: str = ""
    runtime_state: str = ""
    artifact_versions: dict[str, Any] = field(default_factory=dict)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..shared.enums.memory_type import MemoryType


@dataclass(slots=True)
class RepositoryQuery:
    """Query contract for repository lookups."""

    project_id: UUID | None = None
    workflow_id: UUID | None = None
    stage: str | None = None
    memory_type: MemoryType | None = None
    tags: list[str] = field(default_factory=list)
    limit: int = 50
    offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

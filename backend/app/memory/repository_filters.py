from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ..shared.enums.memory_type import MemoryType


@dataclass(slots=True)
class RepositoryFilter:
    """A simple filter for repository searches."""

    project_id: UUID | None = None
    workflow_id: UUID | None = None
    stage: str | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

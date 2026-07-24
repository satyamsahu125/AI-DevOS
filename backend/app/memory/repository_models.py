from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from ..shared.enums.memory_type import MemoryType


@dataclass(slots=True)
class MemoryRecord:
    """A persisted memory record."""

    memory_id: UUID = field(default_factory=uuid4)
    project_id: UUID | None = None
    workflow_id: UUID | None = None
    stage: str | None = None
    memory_type: MemoryType = MemoryType.Runtime
    title: str = ""
    content: str = ""
    summary: str = ""
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class MemorySearchResult:
    """A repository search result payload."""

    items: list[MemoryRecord] = field(default_factory=list)
    total: int = 0


@dataclass(slots=True)
class MemoryPage:
    """A paged view over memory records."""

    items: list[MemoryRecord] = field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..enums.memory_type import MemoryType


@dataclass
class MemoryEntry:
    entry_id: str
    memory_type: MemoryType = MemoryType.Runtime
    content: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

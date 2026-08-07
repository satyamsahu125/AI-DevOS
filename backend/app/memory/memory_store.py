from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryStore:
    """A lightweight in-memory store for runtime memory records."""

    records: dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.records[key] = value

    def get(self, key: str) -> Any | None:
        return self.records.get(key)

    def delete(self, key: str) -> None:
        self.records.pop(key, None)

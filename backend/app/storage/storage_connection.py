from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StorageConnection:
    """Represents a storage connection handle."""

    connected: bool = False
    driver: str = "memory"
    metadata: dict[str, Any] = field(default_factory=dict)

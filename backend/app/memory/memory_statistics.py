from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryStatistics:
    """Represents basic memory runtime statistics."""

    count: int = 0
    indexed: int = 0
    cached: int = 0

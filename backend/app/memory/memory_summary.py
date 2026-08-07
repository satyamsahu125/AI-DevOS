from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemorySummary:
    """A lightweight summary payload that can be injected into prompt context."""

    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

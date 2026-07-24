from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeContext:
    """Context object used by the execution runtime."""

    stage_name: str
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

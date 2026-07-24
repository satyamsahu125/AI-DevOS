from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryContext:
    """A structured container for memory context sent to prompt builders."""

    context_id: str = ""
    workflow_memory: list[Any] = field(default_factory=list)
    stage_memory: list[Any] = field(default_factory=list)
    session_memory: list[Any] = field(default_factory=list)
    long_term_memory: list[Any] = field(default_factory=list)
    summary: str = ""
    estimated_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

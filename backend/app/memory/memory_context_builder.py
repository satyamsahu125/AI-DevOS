from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .memory_context import MemoryContext


@dataclass(slots=True)
class MemoryContextBuilder:
    """Builds a memory context payload from available memory inputs."""

    metadata: dict[str, Any] = field(default_factory=dict)

    def build(self, summary: str = "") -> MemoryContext:
        return MemoryContext(
            context_id="memory-context",
            workflow_memory=[],
            stage_memory=[],
            session_memory=[],
            long_term_memory=[],
            summary=summary,
            estimated_tokens=max(1, len(summary.split())),
            metadata=self.metadata,
        )

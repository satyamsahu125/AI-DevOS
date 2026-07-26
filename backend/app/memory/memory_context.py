from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryContext:
    """Structured container for memory context passed to prompt builders.

    Used by memory/memory_context_builder.py to assemble per-stage context
    slices from WorkflowMemory, SessionMemory, and LongTermMemory.

    NOTE: This class is NOT used in the live pipeline (WorkflowEngine.run() does
    not call ContextManager or MemoryContextBuilder). It is retained because
    memory_context_builder.py imports it. Once the pipeline integrates ContextManager,
    this will become a live data carrier.
    """

    context_id: str = ""
    workflow_memory: list[Any] = field(default_factory=list)
    stage_memory: list[Any] = field(default_factory=list)
    session_memory: list[Any] = field(default_factory=list)
    long_term_memory: list[Any] = field(default_factory=list)
    summary: str = ""
    estimated_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

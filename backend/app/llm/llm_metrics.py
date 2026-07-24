from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LLMMetrics:
    """Simple metrics capture for LLM manager execution."""

    requests: int = 0
    retries: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    last_provider: str = ""
    last_model: str = ""

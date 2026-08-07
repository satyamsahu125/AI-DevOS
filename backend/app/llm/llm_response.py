from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    """Normalized response model for LLM execution."""

    response_id: str
    provider: str
    model: str
    content: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    latency: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

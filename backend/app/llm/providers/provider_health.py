from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class ProviderHealth:
    """Health result returned by a provider."""

    status: str = "ok"
    provider: str = ""
    latency: float = 0.0
    reachable: bool = True
    models_loaded: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

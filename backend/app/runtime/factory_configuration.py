from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FactoryConfiguration:
    """Configuration for the runtime agent factory."""

    agent_types: dict[str, type[Any]] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)

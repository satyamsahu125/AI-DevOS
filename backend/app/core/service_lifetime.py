from __future__ import annotations

from enum import Enum


class ServiceLifetime(str, Enum):
    """Supported dependency lifetimes."""

    Singleton = "singleton"
    Scoped = "scoped"
    Transient = "transient"

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .service_lifetime import ServiceLifetime


@dataclass(slots=True)
class ServiceRegistration:
    """A registration entry for the dependency container."""

    key: str
    implementation: type[Any] | Any
    lifetime: ServiceLifetime = ServiceLifetime.Singleton
    dependencies: list[str] = field(default_factory=list)

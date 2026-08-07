from __future__ import annotations

from dataclasses import dataclass

from ..agents.registry import AgentRegistry
from .dependency_container import DependencyContainer
from .service_registry import ServiceRegistry


@dataclass(slots=True)
class Runtime:
    """Runtime container returned by the bootstrap process."""

    service_registry: ServiceRegistry
    container: DependencyContainer
    agent_registry: AgentRegistry

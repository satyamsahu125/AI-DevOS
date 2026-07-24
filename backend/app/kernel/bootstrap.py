from __future__ import annotations

import logging

from ..agents.registry import AgentRegistry
from ..config.manager import ConfigurationManager
from ..core.dependency_container import DependencyContainer
from ..core.dependency_descriptor import DependencyDescriptor
from ..core.runtime import Runtime
from ..core.service_registry import ServiceRegistry
from .container import Container

logger = logging.getLogger(__name__)


class Bootstrap:
    """Initializes the application runtime: builds the kernel Container and registers
    the documented services (configuration/llm/artifact managers, agent registry) with
    a ServiceRegistry/DependencyContainer, returning the resulting Runtime.
    """

    def __init__(self, container: Container | None = None) -> None:
        """Wire the kernel Container this bootstrap builds, and the service-registration state."""
        self._container = container or Container()
        self._service_registry = ServiceRegistry()
        self._dependency_container = DependencyContainer(self._service_registry)
        self._agent_registry = AgentRegistry()

    def initialize(self) -> Runtime:
        """Build the kernel Container, register documented services/agents, and return the Runtime."""
        logger.info("bootstrap initializing")
        self._container.build()

        self._service_registry.register_manager("configuration_manager", lambda: ConfigurationManager())
        self._service_registry.register_manager("llm_manager", self._create_llm_manager)
        self._service_registry.register_manager("artifact_manager", self._create_artifact_manager)
        self._service_registry.register_registry("agent_registry", lambda: self._agent_registry)
        self._service_registry.register_runtime_component(
            "runtime", lambda: Runtime(self._service_registry, self._dependency_container, self._agent_registry)
        )

        for name in ("configuration_manager", "llm_manager", "artifact_manager", "agent_registry", "runtime"):
            self._dependency_container.register(
                DependencyDescriptor(name=name, factory=self._make_resolver(name))
            )

        self._agent_registry.register("product_owner", "ProductOwnerAgent")
        self._agent_registry.register("reviewer", "Reviewer")

        logger.debug("bootstrap complete: services=%s", self._service_registry.list_services())
        return Runtime(self._service_registry, self._dependency_container, self._agent_registry)

    def _make_resolver(self, name: str):
        return lambda: self._dependency_container.resolve(name)

    @staticmethod
    def _create_llm_manager():
        from ..llm.manager import LLMManager

        return LLMManager()

    @staticmethod
    def _create_artifact_manager():
        from ..artifact.manager import ArtifactManager

        return ArtifactManager()

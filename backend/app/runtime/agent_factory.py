from __future__ import annotations

from typing import Any

from ..agents.architect import ArchitectAgent
from ..agents.backend import BackendDeveloperAgent
from ..agents.base_agent import BaseAgent
from ..agents.devops import DevOpsAgent
from ..agents.frontend import FrontendDeveloperAgent
from ..agents.product_owner import ProductOwnerAgent
from ..agents.qa import QAAgent
from ..shared.exceptions import DependencyException
from .constructor_validation import ConstructorValidation
from .dependency_provider import DependencyProvider
from .factory_configuration import FactoryConfiguration


class AgentFactory:
    """Constructs runtime agents with validated dependencies."""

    def __init__(self, provider: DependencyProvider | None = None, validator: ConstructorValidation | None = None, configuration: FactoryConfiguration | None = None) -> None:
        self.provider = provider or DependencyProvider()
        self.validator = validator or ConstructorValidation()
        self.configuration = configuration or FactoryConfiguration(
            agent_types={
                "product_owner": ProductOwnerAgent,
                "reviewer": ProductOwnerAgent,
                "architect": ArchitectAgent,
                "planner": ArchitectAgent,
                "backend": BackendDeveloperAgent,
                "frontend": FrontendDeveloperAgent,
                "qa": QAAgent,
                "devops": DevOpsAgent,
            },
            dependencies=self.provider.provide(),
        )

    def create(self, agent_type: str) -> BaseAgent:
        normalized = agent_type.lower().replace("-", "_").replace(" ", "_")
        if normalized not in self.configuration.agent_types:
            raise DependencyException(f"unknown agent type: {agent_type}")
        implementation = self.configuration.agent_types[normalized]
        constructor = getattr(implementation, "__init__", None)
        self.validator.validate(constructor, self.configuration.dependencies)
        instance = implementation(**self._resolve_dependencies(implementation))
        return instance

    def create_product_owner(self) -> BaseAgent:
        return self.create("product_owner")

    def create_reviewer(self) -> BaseAgent:
        return self.create("reviewer")

    def create_architect(self) -> BaseAgent:
        return self.create("architect")

    def create_planner(self) -> BaseAgent:
        return self.create("planner")

    def create_backend(self) -> BaseAgent:
        return self.create("backend")

    def create_frontend(self) -> BaseAgent:
        return self.create("frontend")

    def create_qa(self) -> BaseAgent:
        return self.create("qa")

    def create_devops(self) -> BaseAgent:
        return self.create("devops")

    def validate(self) -> None:
        if not self.configuration.agent_types:
            raise DependencyException("factory configuration is empty")

    def _resolve_dependencies(self, implementation: type[Any]) -> dict[str, Any]:
        constructor_parameters = self._constructor_parameters(implementation)
        dependencies: dict[str, Any] = {}
        for name in constructor_parameters:
            if name in self.configuration.dependencies:
                dependencies[name] = self.configuration.dependencies[name]
            elif name == "prompt_builder":
                from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
                dependencies[name] = ProductOwnerPromptBuilder()
        return dependencies

    def _constructor_parameters(self, implementation: type[Any]) -> set[str]:
        constructor = getattr(implementation, "__init__", None)
        if constructor is None:
            return set()
        signature = getattr(constructor, "__code__", None)
        if signature is None:
            return set()
        return set(signature.co_varnames[1:signature.co_argcount])

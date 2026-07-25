from __future__ import annotations

import logging

from ..shared.exceptions import DependencyException
from .architect import ArchitectAgent
from .backend import BackendDeveloperAgent
from .base_agent import BaseAgent
from .clarification import ClarificationAgent
from .designer import DesignerAgent
from .devops import DevOpsAgent
from .document import DocumentAgent
from .file_planner import FileStructurePlannerAgent
from .frontend import FrontendDeveloperAgent
from .product_owner import ProductOwnerAgent
from .qa import QAAgent
from .registry import AgentRegistry
from .resolver import AgentResolver
from .retro import RetroAgent
from .security import SecurityAgent
from .sprint_planner import SprintPlannerAgent
from .strategic_review import StrategicReviewAgent
from .validation import AgentValidation

logger = logging.getLogger(__name__)


class AgentFactory:
    """Constructs runtime agent instances for a workflow stage.

    Resolves a stage name (e.g. "ProductOwner") to a registered agent
    implementation and constructs exactly one instance of it per call.
    """

    def __init__(self, registry: AgentRegistry | None = None, resolver: AgentResolver | None = None, validator: AgentValidation | None = None) -> None:
        """Wire the registry, resolver, and validator used to construct agents, then register the default agent set."""
        self.registry = registry or AgentRegistry()
        self.resolver = resolver or AgentResolver()
        self.validator = validator or AgentValidation()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the documented agent implementations under their canonical names."""
        self.registry.register("product_owner", ProductOwnerAgent)
        self.registry.register("architect", ArchitectAgent)
        self.registry.register("backend", BackendDeveloperAgent)
        self.registry.register("frontend", FrontendDeveloperAgent)
        self.registry.register("qa", QAAgent)
        self.registry.register("devops", DevOpsAgent)
        self.registry.register("strategic_review", StrategicReviewAgent)
        self.registry.register("designer", DesignerAgent)
        self.registry.register("security", SecurityAgent)
        self.registry.register("file_planner", FileStructurePlannerAgent)
        self.registry.register("document", DocumentAgent)
        self.registry.register("retro", RetroAgent)
        self.registry.register("clarification", ClarificationAgent)
        self.registry.register("sprint_planner", SprintPlannerAgent)

    def create(self, stage_name: str) -> BaseAgent:
        """Resolve stage_name to a registered agent and construct a new instance of it."""
        self.validator.validate_name(stage_name)
        agent_name = self.resolver.resolve(stage_name)
        if not self.registry.has(agent_name):
            raise DependencyException(f"agent {agent_name} is not registered")
        implementation = self.registry.resolve(agent_name)
        logger.info("agent factory creating agent: stage=%s agent=%s", stage_name, agent_name)
        if isinstance(implementation, type):
            return implementation()
        return implementation

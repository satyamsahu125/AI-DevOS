from __future__ import annotations

import logging

from ..shared.exceptions import DependencyException
from .architect import ArchitectAgent
from .backend import BackendDeveloperAgent
from .base_agent import BaseAgent
from .bug_analyst import BugAnalystAgent
from .clarification import ClarificationAgent
from .integration_developer import IntegrationDeveloperAgent
from .designer import DesignerAgent
from .devops import DevOpsAgent, ProductionDeployAgent
from .document import DocumentAgent
from .file_planner import FileStructurePlannerAgent
from .frontend import FrontendDeveloperAgent
from .product_owner import ProductOwnerAgent
from .qa import QAAgent
from .registry import AgentRegistry
from .resolver import AgentResolver
from .retro import RetroAgent
from .scrum_master import ScrumMasterAgent
from .security import SecurityAgent
from .sprint_deploy import SprintDeployAgent
from .sprint_planner import SprintPlannerAgent
from .sprint_review import SprintReviewAgent
from .strategic_review import StrategicReviewAgent
from .tech_lead import TechLeadAgent
from .validation import AgentValidation

logger = logging.getLogger(__name__)


class AgentFactory:
    """Constructs runtime agent instances for a workflow stage.

    Resolves a stage name (e.g. "ProductOwner") to a registered agent
    implementation and constructs exactly one instance of it per call.
    """

    def __init__(self, registry: AgentRegistry | None = None, resolver: AgentResolver | None = None, validator: AgentValidation | None = None, llm_manager=None) -> None:
        """Wire the registry, resolver, and validator used to construct agents, then register the default agent set."""
        self.registry = registry or AgentRegistry()
        self.resolver = resolver or AgentResolver()
        self.validator = validator or AgentValidation()
        self._llm_manager = llm_manager
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the documented agent implementations under their canonical names."""
        self.registry.register("product_owner", ProductOwnerAgent)
        self.registry.register("architect", ArchitectAgent)
        self.registry.register("backend", BackendDeveloperAgent)
        self.registry.register("frontend", FrontendDeveloperAgent)
        self.registry.register("qa", QAAgent)
        self.registry.register("devops", DevOpsAgent)
        # FUTURE (RELEASE phase): ProductionDeployAgent is an alias for DevOpsAgent
        # reserved for the post-sprint production promotion step.  It is not wired
        # into any pipeline stage yet — registration keeps the factory consistent
        # so the RELEASE supervisor can call factory.create("production_deploy")
        # when that phase is implemented.
        self.registry.register("production_deploy", ProductionDeployAgent)
        self.registry.register("strategic_review", StrategicReviewAgent)
        self.registry.register("designer", DesignerAgent)
        self.registry.register("security", SecurityAgent)
        self.registry.register("file_planner", FileStructurePlannerAgent)
        self.registry.register("document", DocumentAgent)
        self.registry.register("retro", RetroAgent)
        self.registry.register("clarification", ClarificationAgent)
        self.registry.register("sprint_planner", SprintPlannerAgent)
        self.registry.register("scrum_master", ScrumMasterAgent)
        self.registry.register("tech_lead", TechLeadAgent)
        self.registry.register("bug_analyst", BugAnalystAgent)
        # sprint_deploy / sprint_review are invoked directly by WorkflowManager._run_sprint
        # (not via engine.run_stage()) because they require extra constructor args
        # (workspace_manager, llm_manager) and call bespoke methods (deploy_sprint,
        # review_sprint) rather than the standard BaseAgent.execute() interface.
        # They are registered here so factory.create() works in tests and so the
        # dependency is explicit and discoverable.
        self.registry.register("sprint_deploy", SprintDeployAgent)
        self.registry.register("sprint_review", SprintReviewAgent)
        # R6: Integration Developer — runs in release phase before QA
        self.registry.register("integration", IntegrationDeveloperAgent)

    def create(self, stage_name: str) -> BaseAgent:
        """Resolve stage_name to a registered agent and construct a new instance of it."""
        self.validator.validate_name(stage_name)
        agent_name = self.resolver.resolve(stage_name)
        if not self.registry.has(agent_name):
            raise DependencyException(f"agent {agent_name} is not registered")
        implementation = self.registry.resolve(agent_name)
        logger.info("agent factory creating agent: stage=%s agent=%s", stage_name, agent_name)
        if isinstance(implementation, type):
            if self._llm_manager is not None:
                return implementation(llm_manager=self._llm_manager)
            return implementation()
        return implementation

from __future__ import annotations

import logging
from pathlib import Path

from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..context.context import ContextManager
from ..core.dependency_container import DependencyContainer
from ..execution.manager import ExecutionManager
from ..llm.manager import LLMManager
from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.learning_loop import LearningLoop
from ..memory.manager import MemoryManager
from ..memory.project_event_log import ProjectEventLog
from ..project.initializer import ProjectInitializer
from ..project.manager import ProjectManager
from ..review.manager import ReviewManager
from ..session.manager import SessionManager
from ..shared.interfaces.agent_interface import AgentInterface
from ..workflow.engine import WorkflowEngine
from ..workflow.execution_state import ExecutionStateRegistry
from ..workflow.retry_policy import RetryPolicy
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from ..workflow.manager import WorkflowManager

logger = logging.getLogger(__name__)


class Container:
    """Hand-wired dependency container used by the live application startup path.

    build() registers every top-level manager as a singleton with a
    DependencyContainer and resolves them from it, instead of instantiating
    each manager directly -- sharing the already-loaded ConfigurationManager
    into LLMManager, the built ArtifactManager into ExecutionManager, and the
    shared KnowledgeMemory/LearningLoop into WorkflowEngine and
    ContextManager, the same sharing the original hand-written wiring
    performed for configuration/artifacts.
    """

    def __init__(self) -> None:
        """Initialize every manager slot to None until build() is called."""
        self._configuration = ConfigurationManager()
        self._dependencies = DependencyContainer()
        self._workspace = None
        self._memory = None
        self._artifact = None
        self._review = None
        self._session = None
        self._context = None
        self._execution = None
        self._workflow = None
        self._project = None
        self._llm = None
        self._knowledge_memory = None
        self._learning_loop = None
        self._project_file_manager = None
        self._event_log = None
        self._registry = []

    def build(self) -> "Container":
        """Load configuration, register every manager as a singleton, and resolve them via DependencyContainer."""
        logger.info("container building")
        settings = self._configuration.load()

        self._dependencies.register_singleton("configuration_manager", lambda: self._configuration)
        self._dependencies.register_singleton("workspace_manager", WorkspaceManager)
        self._dependencies.register_singleton("memory_manager", MemoryManager)
        self._dependencies.register_singleton(
            "artifact_manager",
            lambda: ArtifactManager(workspace_manager=self._dependencies.resolve("workspace_manager")),
        )
        self._dependencies.register_singleton("review_manager", ReviewManager)
        self._dependencies.register_singleton("session_manager", SessionManager)
        self._dependencies.register_singleton(
            "project_file_manager",
            lambda: ProjectFileManager(self._dependencies.resolve("workspace_manager")),
        )
        self._dependencies.register_singleton("event_log", ProjectEventLog)
        self._dependencies.register_singleton(
            "knowledge_memory",
            lambda: KnowledgeMemory(db_path=Path(settings.knowledge_db)),
        )
        self._dependencies.register_singleton(
            "learning_loop",
            lambda: LearningLoop(
                knowledge_memory=self._dependencies.resolve("knowledge_memory"),
                db_path=Path(settings.learning_db),
            ),
        )
        self._dependencies.register_singleton(
            "context_manager",
            lambda: ContextManager(
                memory_manager=self._dependencies.resolve("memory_manager"),
                learning_loop=self._dependencies.resolve("learning_loop"),
            ),
        )
        self._dependencies.register_singleton(
            "llm_manager",
            lambda: LLMManager(config_manager=self._dependencies.resolve("configuration_manager")),
        )
        self._dependencies.register_singleton(
            "execution_manager",
            lambda: ExecutionManager(self._dependencies.resolve("artifact_manager")),
        )
        self._dependencies.register_singleton("execution_state", ExecutionStateRegistry)
        self._dependencies.register_singleton(
            "workflow_engine",
            lambda: WorkflowEngine(
                execution_manager=self._dependencies.resolve("execution_manager"),
                learning_loop=self._dependencies.resolve("learning_loop"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                retry_policy=RetryPolicy(max_retries=settings.runtime.retry_limit),
                event_log=self._dependencies.resolve("event_log"),
                execution_state=self._dependencies.resolve("execution_state"),
            ),
        )
        self._dependencies.register_singleton(
            "workflow_manager",
            lambda: WorkflowManager(
                engine=self._dependencies.resolve("workflow_engine"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                execution_state=self._dependencies.resolve("execution_state"),
            ),
        )
        self._dependencies.register_singleton(
            "project_initializer",
            lambda: ProjectInitializer(workflow_manager=self._dependencies.resolve("workflow_manager")),
        )
        self._dependencies.register_singleton(
            "project_manager",
            lambda: ProjectManager(initializer=self._dependencies.resolve("project_initializer")),
        )

        self._workspace = self._dependencies.resolve("workspace_manager")
        self._memory = self._dependencies.resolve("memory_manager")
        self._artifact = self._dependencies.resolve("artifact_manager")
        self._review = self._dependencies.resolve("review_manager")
        self._session = self._dependencies.resolve("session_manager")
        self._knowledge_memory = self._dependencies.resolve("knowledge_memory")
        self._learning_loop = self._dependencies.resolve("learning_loop")
        self._project_file_manager = self._dependencies.resolve("project_file_manager")
        self._event_log = self._dependencies.resolve("event_log")
        self._context = self._dependencies.resolve("context_manager")
        self._llm = self._dependencies.resolve("llm_manager")
        self._execution = self._dependencies.resolve("execution_manager")
        self._workflow = self._dependencies.resolve("workflow_manager")
        self._project = self._dependencies.resolve("project_manager")
        self._registry = [self._project, self._workflow, self._execution, self._session, self._review, self._llm]
        logger.debug("container built: services=%s", self._dependencies.registry.list_services())
        return self

    def resolve(self) -> "Container":
        """Return this already-built container (present for documented-interface compatibility)."""
        return self

    @property
    def configuration(self) -> ConfigurationManager:
        """Return the shared ConfigurationManager."""
        return self._configuration

    @property
    def project_manager(self) -> ProjectManager:
        """Return the resolved ProjectManager singleton."""
        return self._project

    @property
    def workflow_manager(self) -> WorkflowManager:
        """Return the resolved WorkflowManager singleton."""
        return self._workflow

    @property
    def execution_manager(self) -> ExecutionManager:
        """Return the resolved ExecutionManager singleton."""
        return self._execution

    @property
    def session_manager(self) -> SessionManager:
        """Return the resolved SessionManager singleton."""
        return self._session

    @property
    def context_manager(self) -> ContextManager:
        """Return the resolved ContextManager singleton."""
        return self._context

    @property
    def memory_manager(self) -> MemoryManager:
        """Return the resolved MemoryManager singleton."""
        return self._memory

    @property
    def review_manager(self) -> ReviewManager:
        """Return the resolved ReviewManager singleton."""
        return self._review

    @property
    def artifact_manager(self) -> ArtifactManager:
        """Return the resolved ArtifactManager singleton."""
        return self._artifact

    @property
    def workspace_manager(self) -> WorkspaceManager:
        """Return the resolved WorkspaceManager singleton."""
        return self._workspace

    @property
    def llm_manager(self) -> LLMManager:
        """Return the resolved LLMManager singleton."""
        return self._llm

    @property
    def knowledge_memory(self) -> KnowledgeMemory:
        """Return the resolved KnowledgeMemory singleton."""
        return self._knowledge_memory

    @property
    def learning_loop(self) -> LearningLoop:
        """Return the resolved LearningLoop singleton."""
        return self._learning_loop

    @property
    def project_file_manager(self) -> ProjectFileManager:
        """Return the resolved ProjectFileManager singleton."""
        return self._project_file_manager

    @property
    def event_log(self) -> ProjectEventLog:
        """Return the resolved ProjectEventLog singleton."""
        return self._event_log

    @property
    def registry(self) -> list[AgentInterface]:
        """Return the list of top-level managers registered for this container."""
        return self._registry

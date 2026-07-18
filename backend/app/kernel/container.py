from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..context.context import ContextManager
from ..execution.manager import ExecutionManager
from ..llm.manager import LLMManager
from ..memory.manager import MemoryManager
from ..project.manager import ProjectManager
from ..review.manager import ReviewManager
from ..session.manager import SessionManager
from ..shared.interfaces.agent_interface import AgentInterface
from ..workspace.manager import WorkspaceManager
from ..workflow.manager import WorkflowManager


class Container:
    def __init__(self) -> None:
        self._configuration = ConfigurationManager()
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
        self._registry = []

    def build(self) -> "Container":
        self._configuration.load()
        self._workspace = WorkspaceManager()
        self._memory = MemoryManager()
        self._artifact = ArtifactManager()
        self._review = ReviewManager()
        self._session = SessionManager()
        self._context = ContextManager()
        self._execution = ExecutionManager(self._artifact)
        self._workflow = WorkflowManager()
        self._project = ProjectManager()
        self._llm = LLMManager()
        self._registry = [self._project, self._workflow, self._execution, self._session, self._review, self._llm]
        return self

    def resolve(self) -> "Container":
        return self

    @property
    def configuration(self) -> ConfigurationManager:
        return self._configuration

    @property
    def project_manager(self) -> ProjectManager:
        return self._project

    @property
    def workflow_manager(self) -> WorkflowManager:
        return self._workflow

    @property
    def execution_manager(self) -> ExecutionManager:
        return self._execution

    @property
    def session_manager(self) -> SessionManager:
        return self._session

    @property
    def context_manager(self) -> ContextManager:
        return self._context

    @property
    def memory_manager(self) -> MemoryManager:
        return self._memory

    @property
    def review_manager(self) -> ReviewManager:
        return self._review

    @property
    def artifact_manager(self) -> ArtifactManager:
        return self._artifact

    @property
    def workspace_manager(self) -> WorkspaceManager:
        return self._workspace

    @property
    def llm_manager(self) -> LLMManager:
        return self._llm

    @property
    def registry(self) -> list[AgentInterface]:
        return self._registry

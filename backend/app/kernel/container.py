from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..agents.backend import BackendDeveloperAgent
from ..execution.code_sandbox import CodeSandbox
from ..agents.chat_router import ChatRouter
from ..agents.clarification import ClarificationAgent
from ..agents.domain_researcher import DomainResearcherAgent
from ..agents.factory import AgentFactory
from ..agents.file_planner import FilePlannerAgent
from ..agents.frontend import FrontendDeveloperAgent
from ..agents.sprint_planner import SprintPlannerAgent
from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..context.context import ContextManager
from ..core.dependency_container import DependencyContainer
from ..execution.file_validator import FileValidator
from ..execution.manager import ExecutionManager
from ..execution.project_reader import ProjectReader
from ..execution.project_validator import ProjectValidator
from ..execution.project_writer import ProjectWriter
from ..intelligence.code_summarizer import CodeSummarizer
from ..intelligence.context_orchestrator import ContextOrchestrator
from ..intelligence.dependency_graph import ProjectDependencyGraph
from ..intelligence.file_indexer import FileIndexer
from ..intelligence.sprint_monitor import SprintMonitor
from ..learning.template_engine import TemplateEngine
from ..llm.manager import LLMManager
from ..llm.model_router import ModelRouter
from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.learning_loop import LearningLoop
from ..memory.lesson_store import LessonStore
from ..memory.manager import MemoryManager
from ..memory.memory_manager import MemoryOrchestrator  # low-level storage coordinator
from ..memory.orchestrator import MemoryOrchestrator as MemoryContextOrchestrator  # high-level context assembler
from ..memory.project_event_log import ProjectEventLog
from ..project.initializer import ProjectInitializer
from ..project.manager import ProjectManager
from ..review.manager import ReviewManager
from ..session.manager import SessionManager
from ..shared.interfaces.agent_interface import AgentInterface
from ..workflow.engine import WorkflowEngine
from ..workflow.execution_state import ExecutionStateRegistry
from ..workflow.manager import WorkflowManager
from ..workflow.retry_engine import IntelligentRetryEngine
from ..workflow.retry_policy import RetryPolicy
from ..execution.preview_manager import PreviewManager
from ..workspace.dependency_pinner import DependencyPinner
from ..workspace.file_registry import FileRegistry
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from ..db.gate_state import build_gate_state_registry  # R10: distributed gate state

logger = logging.getLogger(__name__)


class Container:
    """Hand-wired dependency container used by the live application startup path.

    build() registers every top-level manager as a singleton with a
    DependencyContainer and resolves them from it, instead of instantiating
    each manager directly.
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
        self._project_writer = None
        self._file_validator = None
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
        # Low-level storage coordinator — kept for any future use, not wired into pipeline.
        self._dependencies.register_singleton("memory_storage_orchestrator", MemoryOrchestrator)
        # High-level context assembler — assembles all four memory layers for WorkflowEngine.
        # Wired into workflow_engine below via memory_orchestrator parameter.
        # Registered AFTER memory_manager, artifact_manager, and workspace_manager.
        self._dependencies.register_singleton(
            "memory_orchestrator",
            lambda: MemoryContextOrchestrator(
                memory_manager=self._dependencies.resolve("memory_manager"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                context_manager=self._dependencies.resolve("context_manager"),  # BUG-5: Layer 3 semantic memory now active
                # Phase 3: wire ContextOrchestrator for Layer 4 (procedural intelligence).
                # context_orchestrator is already wired — it handles its own errors gracefully.
                context_orchestrator=self._dependencies.resolve("context_orchestrator"),
                # Phase 7: wire LearningLoop + LessonStore for approval/rejection recording.
                learning_loop=self._dependencies.resolve("learning_loop"),
                lesson_store=self._dependencies.resolve("lesson_store"),
            ),
        )
        self._dependencies.register_singleton("review_manager", ReviewManager)
        self._dependencies.register_singleton("session_manager", SessionManager)
        self._dependencies.register_singleton(
            "project_file_manager",
            lambda: ProjectFileManager(self._dependencies.resolve("workspace_manager")),
        )
        self._dependencies.register_singleton(
            "file_registry",
            lambda: FileRegistry(workspace_manager=self._dependencies.resolve("workspace_manager")),
        )
        # Phase 5: CodeSandbox — enabled by default (SANDBOX_ENABLED=true since R2).
        # Runs lint/test/build on generated code after each sprint.
        self._dependencies.register_singleton(
            "code_sandbox",
            lambda: CodeSandbox(workspace_manager=self._dependencies.resolve("workspace_manager")),
        )
        # R2: DependencyPinner — pins requirements.txt and package.json to exact stable versions.
        self._dependencies.register_singleton(
            "dependency_pinner",
            lambda: DependencyPinner(),
        )
        # R5: PreviewManager — manages subprocess preview of generated apps.
        # Enabled only when PREVIEW_ENABLED=true (default false for production).
        self._dependencies.register_singleton(
            "preview_manager",
            lambda: PreviewManager(),
        )
        self._dependencies.register_singleton(
            "project_writer",
            lambda: ProjectWriter(
                self._dependencies.resolve("workspace_manager"),
                file_indexer=self._dependencies.resolve("file_indexer"),
            ),
        )
        self._dependencies.register_singleton(
            "project_reader",
            lambda: ProjectReader(self._dependencies.resolve("workspace_manager")),
        )
        self._dependencies.register_singleton("file_validator", FileValidator)
        from ..events.broadcaster import broadcaster
        self._dependencies.register_singleton("broadcaster", lambda: broadcaster)
        self._dependencies.register_singleton("event_log", ProjectEventLog)
        # R10: gate state registry — Redis-backed when REDIS_URL is set, in-memory otherwise.
        # Non-fatal: any error here must not block container build.
        try:
            self._dependencies.register_singleton(
                "gate_state_registry",
                lambda: build_gate_state_registry(),
            )
        except Exception as _gsr_exc:
            logger.warning("container: gate_state_registry registration failed (non-fatal): %s", _gsr_exc)
            from ..db.gate_state import InMemoryGateStateRegistry
            self._dependencies.register_singleton(
                "gate_state_registry",
                lambda: InMemoryGateStateRegistry(),
            )
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
            "lesson_store",
            lambda: LessonStore(db_path=Path(settings.lessons_db)),
        )
        # BUG-5 fix: re-enable ContextManager (Layer 3 semantic memory).
        # ContextManager provides cross-project patterns + lessons to MemoryOrchestrator.
        # Wrapped in try/except so a failure here never blocks server startup.
        try:
            self._dependencies.register_singleton(
                "context_manager",
                lambda: ContextManager(
                    memory_manager=self._dependencies.resolve("memory_manager"),
                    learning_loop=self._dependencies.resolve("learning_loop"),
                    lesson_store=self._dependencies.resolve("lesson_store"),
                    workspace_manager=self._dependencies.resolve("workspace_manager"),
                    prompt_analyzer=self._dependencies.resolve("prompt_analyzer"),
                ),
            )
        except Exception as _ctx_exc:
            logger.warning("container: ContextManager registration failed (non-fatal): %s", _ctx_exc)
            self._dependencies.register_singleton("context_manager", lambda: None)
        from ..llm.cost_tracker import CostTracker
        # Phase 6: anchored path — safe when uvicorn is started from any directory.
        _data_dir = Path(__file__).resolve().parents[3] / "data"
        _data_dir.mkdir(parents=True, exist_ok=True)
        self._dependencies.register_singleton(
            "cost_tracker",
            lambda: CostTracker(str(_data_dir / "costs.db")),
        )

        # ── Intelligence Layer ────────────────────────────────────────────────
        # Phase 6: anchored path — safe when uvicorn is started from any directory.
        self._dependencies.register_singleton(
            "file_indexer",
            lambda: FileIndexer(db_path=str(_data_dir / "file_index.db")),
        )
        self._dependencies.register_singleton(
            "dependency_graph",
            lambda: ProjectDependencyGraph(
                file_indexer=self._dependencies.resolve("file_indexer"),
            ),
        )
        self._dependencies.register_singleton(
            "code_summarizer",
            lambda: CodeSummarizer(
                file_indexer=self._dependencies.resolve("file_indexer"),
            ),
        )
        self._dependencies.register_singleton(
            "context_orchestrator",
            lambda: ContextOrchestrator(
                file_indexer=self._dependencies.resolve("file_indexer"),
                dependency_graph=self._dependencies.resolve("dependency_graph"),
                code_summarizer=self._dependencies.resolve("code_summarizer"),
                knowledge_memory=self._dependencies.resolve("knowledge_memory"),
                lesson_store=self._dependencies.resolve("lesson_store"),  # Phase 3: now properly registered
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
            ),
        )
        self._dependencies.register_singleton(
            "sprint_monitor",
            lambda: SprintMonitor(
                file_indexer=self._dependencies.resolve("file_indexer"),
                dependency_graph=self._dependencies.resolve("dependency_graph"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
            ),
        )
        self._dependencies.register_singleton(
            "domain_researcher_agent",
            lambda: DomainResearcherAgent(llm_manager=self._dependencies.resolve("llm_manager")),
        )
        # ─────────────────────────────────────────────────────────────────────
        from ..learning.performance_scorer import AgentPerformanceScorer
        self._dependencies.register_singleton(
            "performance_scorer",
            lambda: AgentPerformanceScorer(
                learning_loop=self._dependencies.resolve("learning_loop"),
                cost_tracker=self._dependencies.resolve("cost_tracker"),
                memory_manager=self._dependencies.resolve("memory_manager"),
            ),
        )
        # Phase 7: ModelRouter — per-stage LLM routing profiles.
        self._dependencies.register_singleton("model_router", ModelRouter)
        # Phase 7: TemplateEngine — structural template extraction and injection.
        self._dependencies.register_singleton(
            "template_engine",
            lambda: TemplateEngine(db_path=Path(settings.learning_db)),
        )
        from ..learning.prompt_analyzer import PromptQualityAnalyzer

        def _build_prompt_analyzer():
            # Phase 3 fix: lesson_store and knowledge_memory are now properly registered.
            # No silent try/except — if they fail to resolve, the error surfaces clearly.
            ls = self._dependencies.resolve("lesson_store")
            km = self._dependencies.resolve("knowledge_memory")
            return PromptQualityAnalyzer(lesson_store=ls, knowledge_memory=km)

        self._dependencies.register_singleton("prompt_analyzer", _build_prompt_analyzer)
        self._dependencies.register_singleton(
            "llm_manager",
            lambda: LLMManager(
                config_manager=self._dependencies.resolve("configuration_manager"),
                cost_tracker=self._dependencies.resolve("cost_tracker"),
                broadcaster=self._dependencies.resolve("broadcaster"),
            ),
        )

        # Singletons for Agents
        self._dependencies.register_singleton(
            "clarification_agent",
            lambda: ClarificationAgent(llm_manager=self._dependencies.resolve("llm_manager")),
        )
        self._dependencies.register_singleton(
            "sprint_planner_agent",
            lambda: SprintPlannerAgent(llm_manager=self._dependencies.resolve("llm_manager")),
        )
        self._dependencies.register_singleton(
            "file_planner_agent",
            lambda: FilePlannerAgent(
                llm_manager=self._dependencies.resolve("llm_manager"),
                file_registry=self._dependencies.resolve("file_registry"),
            ),
        )
        self._dependencies.register_singleton(
            "backend_developer_agent",
            lambda: BackendDeveloperAgent(
                llm_manager=self._dependencies.resolve("llm_manager"),
                project_writer=self._dependencies.resolve("project_writer"),
                validator=self._dependencies.resolve("file_validator"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                file_indexer=self._dependencies.resolve("file_indexer"),
            ),
        )
        self._dependencies.register_singleton(
            "frontend_developer_agent",
            lambda: FrontendDeveloperAgent(
                llm_manager=self._dependencies.resolve("llm_manager"),
                project_writer=self._dependencies.resolve("project_writer"),
                validator=self._dependencies.resolve("file_validator"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                file_indexer=self._dependencies.resolve("file_indexer"),
            ),
        )

        self._dependencies.register_singleton(
            "execution_manager",
            lambda: ExecutionManager(self._dependencies.resolve("artifact_manager")),
        )
        self._dependencies.register_singleton("execution_state", ExecutionStateRegistry)
        self._dependencies.register_singleton(
            "retry_engine",
            lambda: IntelligentRetryEngine(
                max_retries=settings.runtime.retry_limit,
                performance_scorer=self._dependencies.resolve("performance_scorer"),
            ),
        )
        def _build_workflow_engine():
            engine = WorkflowEngine(
                execution_manager=self._dependencies.resolve("execution_manager"),
                learning_loop=self._dependencies.resolve("learning_loop"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                retry_policy=RetryPolicy(max_retries=settings.runtime.retry_limit),
                event_log=self._dependencies.resolve("event_log"),
                execution_state=self._dependencies.resolve("execution_state"),
                broadcaster=self._dependencies.resolve("broadcaster"),
                context_orchestrator=self._dependencies.resolve("context_orchestrator"),
                config_manager=self._dependencies.resolve("configuration_manager"),
                memory_orchestrator=self._dependencies.resolve("memory_orchestrator"),
                retry_engine=self._dependencies.resolve("retry_engine"),
            )
            # BUG-5 fix: wire ModelRouter and TemplateEngine (built but never called before).
            # Set directly since WorkflowEngine.__init__ doesn't accept them as params (avoids
            # breaking the constructor signature for existing tests).
            engine.model_router = self._dependencies.resolve("model_router")
            engine.template_engine = self._dependencies.resolve("template_engine")
            return engine

        self._dependencies.register_singleton("workflow_engine", _build_workflow_engine)
        self._dependencies.register_singleton(
            "agent_factory", 
            lambda: AgentFactory(llm_manager=self._dependencies.resolve("llm_manager"))
        )
        self._dependencies.register_singleton(
            "project_validator",
            lambda: ProjectValidator(workspace_manager=self._dependencies.resolve("workspace_manager")),
        )
        from ..workflow.impact_analyzer import ImpactAnalyzer
        self._dependencies.register_singleton(
            "impact_analyzer",
            lambda: ImpactAnalyzer(
                llm_manager=self._dependencies.resolve("llm_manager"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                file_indexer=self._dependencies.resolve("file_indexer"),
                dep_graph=self._dependencies.resolve("dependency_graph"),
                code_summarizer=self._dependencies.resolve("code_summarizer"),
            ),
        )
        self._dependencies.register_singleton(
            "workflow_manager",
            lambda: WorkflowManager(
                engine=self._dependencies.resolve("workflow_engine"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
                execution_state=self._dependencies.resolve("execution_state"),
                agent_factory=self._dependencies.resolve("agent_factory"),
                project_validator=self._dependencies.resolve("project_validator"),
                impact_analyzer=self._dependencies.resolve("impact_analyzer"),
                container=self,  # gives _run_sprint() access to DI-wired developer agents
                sprint_monitor=self._dependencies.resolve("sprint_monitor"),
                domain_researcher=self._dependencies.resolve("domain_researcher_agent"),
                config_manager=self._dependencies.resolve("configuration_manager"),
                file_indexer=self._dependencies.resolve("file_indexer"),        # Phase 3: intelligence trigger
                code_sandbox=self._dependencies.resolve("code_sandbox"),        # Phase 5: code execution sandbox
                dependency_pinner=self._dependencies.resolve("dependency_pinner"),  # R2: pin dependency versions
                preview_manager=self._dependencies.resolve("preview_manager"),      # R5: live app preview
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
        self._dependencies.register_singleton(
            "chat_router",
            lambda: ChatRouter(
                llm_manager=self._dependencies.resolve("llm_manager"),
                artifact_manager=self._dependencies.resolve("artifact_manager"),
                workflow_manager=self._dependencies.resolve("workflow_manager"),
                workspace_manager=self._dependencies.resolve("workspace_manager"),
            ),
        )

        self._workspace = self._dependencies.resolve("workspace_manager")
        self._memory = self._dependencies.resolve("memory_manager")
        self._artifact = self._dependencies.resolve("artifact_manager")
        self._review = self._dependencies.resolve("review_manager")
        self._session = self._dependencies.resolve("session_manager")
        self._knowledge_memory = self._dependencies.resolve("knowledge_memory")
        self._learning_loop = self._dependencies.resolve("learning_loop")
        self._project_file_manager = self._dependencies.resolve("project_file_manager")
        self._project_writer = self._dependencies.resolve("project_writer")
        self._file_validator = self._dependencies.resolve("file_validator")
        self._event_log = self._dependencies.resolve("event_log")
        # BUG-5 fix: resolve ContextManager (now active; was None before).
        try:
            self._context = self._dependencies.resolve("context_manager")
        except Exception:
            self._context = None
        self._llm = self._dependencies.resolve("llm_manager")
        self._execution = self._dependencies.resolve("execution_manager")
        self._workflow = self._dependencies.resolve("workflow_manager")
        self._project = self._dependencies.resolve("project_manager")
        self._registry = [self._project, self._workflow, self._execution, self._session, self._review, self._llm]
        logger.debug("container built: services=%s", self._dependencies.registry.list_services())
        return self

    def resolve(self, service_name: str | None = None) -> Any:
        """Return this container or resolve a named service."""
        if service_name is not None:
            return self._dependencies.resolve(service_name)
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
    def context_manager(self) -> ContextManager | None:
        """Returns None — ContextManager is not wired into the live pipeline yet."""
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
    def knowledge_memory(self) -> KnowledgeMemory:
        return self._knowledge_memory

    @property
    def learning_loop(self) -> LearningLoop:
        return self._learning_loop

    @property
    def project_file_manager(self) -> ProjectFileManager:
        return self._project_file_manager

    @property
    def project_validator(self) -> ProjectValidator:
        return self._dependencies.resolve("project_validator")

    @property
    def project_writer(self) -> ProjectWriter:
        return self._project_writer

    @property
    def cost_tracker(self):
        return self._dependencies.resolve("cost_tracker")

    @property
    def performance_scorer(self):
        return self._dependencies.resolve("performance_scorer")

    @property
    def prompt_analyzer(self):
        return self._dependencies.resolve("prompt_analyzer")

    @property
    def impact_analyzer(self):
        return self._dependencies.resolve("impact_analyzer")

    @property
    def chat_router(self) -> ChatRouter:
        return self._dependencies.resolve("chat_router")

    @property
    def file_validator(self) -> FileValidator:
        return self._file_validator

    @property
    def event_log(self) -> ProjectEventLog:
        return self._event_log

    @property
    def registry(self) -> list[AgentInterface]:
        return self._registry

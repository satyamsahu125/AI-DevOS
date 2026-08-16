"""WorkflowManager — thin coordinator: state machine entry point.

Single responsibility: read ProjectState → route to the correct handler.

Delegates everything else:
  Q&A flow            → QAOrchestrator
  Requirement changes → ChangeManager
  Pipeline execution  → PipelineSupervisor

Has no knowledge of:
  - How stages are executed (WorkflowEngine)
  - How sprints are run (SprintExecutor)
  - How Q&A questions are generated (QAOrchestrator)
  - How impact analysis works (ChangeManager)
"""
from __future__ import annotations

import logging
from typing import Any

from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..workspace.manager import WorkspaceManager
from .engine import WorkflowEngine
from .execution_state import ExecutionStateRegistry
from .pipeline_supervisor import PipelineSupervisor
from .stage_lookup import resolve_stage_name

logger = logging.getLogger(__name__)

# Stages that are implied complete by the current pipeline state.
# Used by _sanitize_stages_completed to prevent gap-sanitizer from wiping
# valid stages on projects that went through the Q&A path.
_STATE_IMPLIED_STAGES: dict[str, tuple[str, ...]] = {
    "requirements_ready":   ("StrategicReview",),
    "architecture_ready":   ("StrategicReview", "ProductOwner"),
    "design_ready":         ("StrategicReview", "ProductOwner", "Architect"),
    "design_review_pending":("StrategicReview", "ProductOwner", "Architect", "Designer"),
    "design_approved":      ("StrategicReview", "ProductOwner", "Architect", "Designer"),
    "sprint_plan_ready":    ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "sprint_in_progress":   ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "all_sprints_complete": ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "qa_complete":          ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "deployable":           ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "done":                 ("StrategicReview", "ProductOwner", "Architect", "Designer",
                             "Security", "SprintPlanning", "ScrumMaster"),
    "resuming_from_change": ("StrategicReview",),
    "change_requested":     ("StrategicReview",),
}


class WorkflowManager:
    """State machine coordinator — reads state, routes to the right handler.

    The only logic that lives here:
      - Duplicate-run guard (execution_state)
      - Stage gap-sanitization on project.json load
      - State routing (EMPTY / CLARIFYING / QA / gate / pipeline)
      - _transition() and _await_gate() for gate pauses

    Everything else is delegated.
    """

    def __init__(
        self,
        engine: WorkflowEngine | None = None,
        workspace_manager: WorkspaceManager | None = None,
        execution_state: ExecutionStateRegistry | None = None,
        qa_orchestrator: Any = None,
        change_manager: Any = None,
        pipeline_supervisor: PipelineSupervisor | None = None,
        # Legacy deps kept so existing container wiring doesn't break
        agent_factory: Any = None,
        project_validator: Any = None,
        impact_analyzer: Any = None,
        container: Any = None,
        sprint_monitor: Any = None,
        domain_researcher: Any = None,
        config_manager: Any = None,
        file_indexer: Any = None,
        dependency_graph: Any = None,
        code_summarizer: Any = None,
        code_sandbox: Any = None,
        dependency_pinner: Any = None,
        preview_manager: Any = None,
    ) -> None:
        from ..workspace.manager import WorkspaceManager as _WM
        from ..artifact.manager import ArtifactManager
        from ..events.broadcaster import broadcaster as default_broadcaster

        self.engine = engine or WorkflowEngine()
        self.workspace_manager = workspace_manager or (
            getattr(self.engine, "workspace_manager", None) or _WM()
        )
        self.execution_state = execution_state or ExecutionStateRegistry()
        self.artifact_manager = getattr(self.engine, "artifact_manager", None) or ArtifactManager(
            workspace_manager=self.workspace_manager,
        )
        self.broadcaster = getattr(self.engine, "broadcaster", None) or default_broadcaster
        self._container = container

        # --- Build ChangeManager first (PipelineSupervisor needs it for BugAnalyst rollback) ---
        if change_manager is not None:
            self._change_manager = change_manager
        else:
            from .change_manager import ChangeManager
            if impact_analyzer is None:
                from .impact_analyzer import ImpactAnalyzer
                impact_analyzer = ImpactAnalyzer(
                    llm_manager=getattr(self.engine, "llm_manager", None),
                    artifact_manager=self.artifact_manager,
                )
            self._change_manager = ChangeManager(
                workspace_manager=self.workspace_manager,
                impact_analyzer=impact_analyzer,
                broadcaster=self.broadcaster,
                transition_fn=self._transition,
            )

        # --- Build PipelineSupervisor ---
        if pipeline_supervisor is not None:
            self._pipeline_supervisor = pipeline_supervisor
        else:
            from .sprint_executor import SprintExecutor
            from ..agents.factory import AgentFactory
            _af = agent_factory or AgentFactory()
            sprint_exec = SprintExecutor(
                engine=self.engine,
                agent_factory=_af,
                workspace_manager=self.workspace_manager,
                artifact_manager=self.artifact_manager,
                sprint_monitor=sprint_monitor,
                broadcaster=self.broadcaster,
                project_writer=getattr(self.engine, "project_writer", None),
                # Phase 1: wire sandbox so SprintExecutor gates sprint success on
                # install → build → test before marking the sprint complete.
                code_sandbox=code_sandbox,
            )
            from ..config.manager import ConfigurationManager
            cfg = config_manager or ConfigurationManager()
            settings = cfg.load() if hasattr(cfg, "load") else None
            self._pipeline_supervisor = PipelineSupervisor(
                workspace=self.workspace_manager,
                engine=self.engine,
                sprint_executor=sprint_exec,
                settings=settings,
                file_indexer=file_indexer,
                dependency_graph=dependency_graph,
                code_summarizer=code_summarizer,
                code_sandbox=code_sandbox,
                dependency_pinner=dependency_pinner,
                preview_manager=preview_manager,
                change_manager=self._change_manager,
                memory_manager=getattr(self.engine, "memory_manager", None),
            )

        # --- Build QAOrchestrator ---
        if qa_orchestrator is not None:
            self._qa_orchestrator = qa_orchestrator
        else:
            from .qa_orchestrator import QAOrchestrator
            from ..agents.factory import AgentFactory
            _af2 = agent_factory or AgentFactory()
            self._qa_orchestrator = QAOrchestrator(
                workspace_manager=self.workspace_manager,
                artifact_manager=self.artifact_manager,
                broadcaster=self.broadcaster,
                agent_factory=_af2,
                pipeline_supervisor=self._pipeline_supervisor,
                execution_state=self.execution_state,
                run_stage_fn=self.run_stage,
                transition_fn=self._transition,
                domain_researcher=domain_researcher,
            )

        # Expose for backward-compat (e.g. project_writer, sprint_monitor).
        self.sprint_monitor = sprint_monitor
        self.domain_researcher = domain_researcher
        self.project_validator = project_validator

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, project_id: str, request: str = "", skip_qa: bool = False) -> PipelineResult:
        """Read current state and advance the pipeline.

        Guards against duplicate concurrent runs.
        """
        if not project_id:
            return PipelineResult(
                project_id="",
                state=ProjectState.FAILED,
                success=False,
                message="project_id is required",
                completed_stages=[],
            )

        if self.execution_state.is_running(project_id):
            logger.warning("duplicate run rejected: project=%s", project_id)
            data = self.workspace_manager.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=self.workspace_manager.get_state(project_id),
                success=False,
                message="A build is already running. Wait or POST /workflow/{id}/stop.",
                completed_stages=list(data.get("stages_completed", [])),
            )

        p_data = self.workspace_manager.load_project_json(project_id) or {}
        if request:
            self.workspace_manager.update_project_json(project_id, {"original_request": request})
        else:
            request = (
                p_data.get("original_request")
                or p_data.get("description")
                or f"Build project {project_id}"
            )

        # Sanitize stages_completed gap (handles crash-recovered projects).
        from .dependency_graph import DependencyGraph
        raw_completed = p_data.get("stages_completed", [])
        current_state_str = p_data.get("state", "")
        stages_completed = self._sanitize_stages_completed(
            raw_completed, DependencyGraph.ordered_stages(), current_state=current_state_str,
        )
        if raw_completed != stages_completed:
            logger.warning(
                "Sanitized stages_completed for %s: %s → %s",
                project_id, raw_completed, stages_completed,
            )
            self.workspace_manager.update_project_json(
                project_id, {"stages_completed": stages_completed},
            )

        state = self.workspace_manager.get_state(project_id)
        self.execution_state.mark_running(project_id)
        self.workspace_manager.update_project_json(project_id, {"stopped": False})
        try:
            if state == ProjectState.EMPTY:
                self._transition(project_id, ProjectState.CLARIFYING)
                state = ProjectState.CLARIFYING

            if state == ProjectState.CLARIFYING:
                return self._qa_orchestrator.handle_clarifying(project_id, request, skip_qa)

            if state in (ProjectState.QA_PENDING, ProjectState.QA_IN_PROGRESS):
                if skip_qa:
                    return self._qa_orchestrator._skip_qa_path(project_id, request)
                return self._qa_orchestrator.handle_qa_flow(project_id, request)

            if state == ProjectState.ARCHITECTURE_REVIEW_PENDING:
                return self._await_gate(project_id, "architecture")
            if state == ProjectState.DESIGN_REVIEW_PENDING:
                return self._await_gate(project_id, "design")
            if state == ProjectState.SPRINT_PLAN_REVIEW_PENDING:
                return self._await_gate(project_id, "sprint_plan")

            return self._pipeline_supervisor.run(project_id, request)
        finally:
            self.execution_state.mark_stopped(project_id)

    # ------------------------------------------------------------------
    # Stage execution (used by QAOrchestrator and PipelineSupervisor)
    # ------------------------------------------------------------------

    def run_stage(self, project_id: str, stage_name: str, content: str) -> WorkflowResult:
        """Run a single stage through WorkflowEngine.

        Note: does NOT call mark_running/mark_stopped — the outer run()
        already holds the execution guard for the entire pipeline duration.
        """
        stage_name = resolve_stage_name(stage_name)
        logger.info("manager.run_stage: project=%s stage=%s", project_id, stage_name)
        result = self.engine.run(project_id, stage_name, content)
        if result.stopped:
            self.workspace_manager.update_project_json(project_id, {"stopped": True})
        return result

    # ------------------------------------------------------------------
    # Requirement change (delegate to ChangeManager)
    # ------------------------------------------------------------------

    def submit_requirement_change(
        self, project_id: str, change_description: str,
    ) -> Any:
        return self._change_manager.submit(project_id, change_description)

    def apply_requirement_change(
        self,
        project_id: str,
        change_id: str,
        confirmed: bool,
        user_comment: str = "",
    ) -> dict:
        return self._change_manager.apply(project_id, change_id, confirmed, user_comment)

    # ------------------------------------------------------------------
    # Validation (kept for backward compat)
    # ------------------------------------------------------------------

    def _run_validation_with_healing(
        self,
        project_id: str,
        original_request: str,
        max_healing_attempts: int = 3,
    ) -> Any:
        """Self-healing validation loop — re-runs BackendDeveloper on fixable errors."""
        from ..execution.project_validator import ValidationResult
        result = None
        for attempt in range(1, max_healing_attempts + 1):
            logger.info("Validation attempt %d/%d for %s", attempt, max_healing_attempts, project_id)
            result = self.project_validator.validate(project_id)
            if result.passed:
                return result
            if attempt < max_healing_attempts and result.fixable_errors:
                error_context = (
                    f"The generated project failed validation (attempt {attempt}/{max_healing_attempts}).\n\n"
                    f"Errors:\n"
                    + "\n".join(f"  - {e}" for e in result.fixable_errors[:5])
                    + "\n\nFix ONLY the files mentioned. Do not rewrite other files."
                )
                logger.warning("Self-healing for %s: %s", project_id, error_context[:200])
                self.run_stage(project_id, "backend", error_context)
            else:
                logger.error("Validation failed after %d attempts for %s", attempt, project_id)
                break
        return result

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _transition(self, project_id: str, new_state: ProjectState) -> None:
        self.workspace_manager.update_state(project_id, new_state)
        logger.info("state transition: project=%s → %s", project_id, new_state)
        data = self.workspace_manager.load_project_json(project_id) or {}
        st_val = new_state.value if hasattr(new_state, "value") else str(new_state)
        self.broadcaster.status_update(
            project_id=project_id,
            state=st_val,
            current_stage=data.get("current_stage"),
            stages_completed=data.get("stages_completed", []),
        )

    def _await_gate(self, project_id: str, gate: str) -> PipelineResult:
        _map = {
            "architecture": ("review_architecture", "Architecture ready for review."),
            "design":       ("review_design",       "Design ready for review."),
            "sprint_plan":  ("review_sprint_plan",  "Sprint plan ready for review."),
        }
        state = self.workspace_manager.get_state(project_id)
        action_needed, message = _map.get(gate, ("review", "Awaiting review."))
        data = self.workspace_manager.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=False,
            requires_user_action=True,
            action_needed=action_needed,
            message=message,
            completed_stages=list(data.get("stages_completed", [])),
        )

    @staticmethod
    def _sanitize_stages_completed(
        stages_completed: list[str],
        stage_order: list[Any],
        current_state: str = "",
    ) -> list[str]:
        """Return a sanitized stages_completed list.

        Top-level stages (those in stage_order / DependencyGraph.STAGE_ORDER) are
        gap-sanitized: the longest contiguous prefix of stage_order that appears in
        stages_completed is kept.  Any gap (a stage in stage_order that is absent from
        stages_completed) stops the prefix — preventing orphaned later stages from
        persisting through a crash-recovery.

        Sprint-internal stages (ScrumMaster, SprintDelta, FileStructurePlanner,
        BackendDeveloper, FrontendDeveloper, SprintDeploy, SprintReview) are NOT in
        stage_order — they are managed by SprintExecutor via DependencyGraph.SPRINT_STAGE_ORDER.
        These stages are appended after the sanitized top-level prefix, preserving them
        so that PipelineSupervisor and SprintExecutor can resume correctly from
        SPRINT_BLOCKED state without re-running already-completed agent stages.
        """
        implied = _STATE_IMPLIED_STAGES.get(current_state, ())
        merged = list(stages_completed)
        for s in implied:
            if s not in merged:
                merged.append(s)

        order = [s.value for s in stage_order]
        order_set = set(order)
        merged_set = set(merged)

        # Sanitize top-level stages: longest contiguous prefix of stage_order
        clean = []
        for stage in order:
            if stage in merged_set:
                clean.append(stage)
            else:
                break

        # Preserve sprint-internal stages (not in top-level stage_order) in their
        # original order from stages_completed.  These must not be gap-sanitized
        # because they live in a separate ordered graph (SPRINT_STAGE_ORDER).
        extras = [s for s in stages_completed if s not in order_set]
        return clean + extras

    # ------------------------------------------------------------------
    # Backward-compat shim (used by tests and container)
    # ------------------------------------------------------------------

    def _run_stage(self, project_id: str, stage_name: str, request: str) -> WorkflowResult:
        return self.run_stage(project_id, stage_name, request)

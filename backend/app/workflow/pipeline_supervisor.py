"""PipelineSupervisor — orchestrates the full 3-phase AI DevOS pipeline.

Replaces the hardcoded state machine in WorkflowManager.run().
Manages three phases:
  1. Discovery: requirements, architecture, design (runs once)
  2. Sprints: iterative implementation (runs N times via SprintSupervisor)
  3. Release: QA, DevOps, Documentation (runs once after all sprints)

Key design:
- Resumes from current state (idempotent, crash-safe)
- Calls engine.run_stage() for discovery and release stages
- Calls sprint_supervisor.run_sprint() for each sprint
- Non-fatal failures in release stages are logged but don't block
- Pauses for user action (design review) when needed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..workspace.manager import WorkspaceManager
from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

# State groupings for phase-based execution
DISCOVERY_STATES = {
    ProjectState.EMPTY,
    ProjectState.CLARIFYING,
    ProjectState.QA_PENDING,
    ProjectState.QA_IN_PROGRESS,
    ProjectState.REQUIREMENTS_READY,
    ProjectState.ARCHITECTURE_READY,
    ProjectState.DESIGN_READY,
    ProjectState.DESIGN_REVIEW_PENDING,
    ProjectState.DESIGN_APPROVED,
}

SPRINT_STATES = {
    ProjectState.SPRINT_PLAN_READY,
    ProjectState.SPRINT_IN_PROGRESS,
    ProjectState.SPRINT_BLOCKED,
}

RELEASE_STATES = {
    ProjectState.ALL_SPRINTS_COMPLETE,
    ProjectState.QA_COMPLETE,
}

from .dependency_graph import DependencyGraph

def get_discovery_stages() -> list[str]:
    """Dynamically get discovery stages from DependencyGraph up to sprint_planner."""
    order = DependencyGraph.STAGE_ORDER
    if not order:
        DependencyGraph._load_config()
        order = DependencyGraph.STAGE_ORDER
    
    stages = []
    for s in order:
        stages.append(s)
        if s == "sprint_planner":
            break
    return stages

def get_release_stages() -> list[str]:
    """Dynamically get release stages from DependencyGraph after sprint_planner."""
    order = DependencyGraph.STAGE_ORDER
    if not order:
        DependencyGraph._load_config()
        order = DependencyGraph.STAGE_ORDER
    
    stages = []
    found_sprint_planner = False
    for s in order:
        if found_sprint_planner:
            stages.append(s)
        if s == "sprint_planner":
            found_sprint_planner = True
    return stages


@dataclass
class _StageResult:
    """Internal result from running a single stage."""
    success: bool
    message: str = ""


class PipelineSupervisor:
    """Orchestrates the full 3-phase pipeline (Discovery → Sprints → Release).

    Replaces the if/elif state machine in WorkflowManager.run().
    to WorkflowManager._run_sprint for sprint-level execution.

    Parameters
    ----------
    workspace : WorkspaceManager
        For reading/writing project state and artifacts.
    engine
        WorkflowEngine instance (calls engine.run_stage() for each stage).
    workflow_manager
        WorkflowManager instance for sprint execution.
    settings
        Settings object with configuration.
    """

    def __init__(
        self,
        workspace,
        engine,
        workflow_manager,
        settings,
    ) -> None:
        self.workspace = workspace
        self.engine = engine
        self.workflow_manager = workflow_manager
        self.settings = settings

    def run(
        self,
        project_id: str,
        request: str,
    ) -> PipelineResult:
        """Execute pipeline from current state, advancing through all phases.

        Resumes from the project's current ProjectState. Safe to call
        multiple times — each call is idempotent per state. Pauses at
        DESIGN_REVIEW_PENDING and SPRINT_BLOCKED states.

        Parameters
        ----------
        project_id : str
            Project identifier.
        request : str
            User-facing request/description for this project.

        Returns
        -------
        PipelineResult
            Result with final state, success flag, and completed stages.
        """
        try:
            return self._run_impl(project_id, request)
        except Exception as exc:
            logger.error(
                "[PipelineSupervisor] pipeline crashed: %s",
                exc,
                exc_info=True,
            )
            try:
                state = self.workspace.get_state(project_id)
                data = self.workspace.load_project_json(project_id) or {}
                stages = list(data.get("stages_completed", []))
            except Exception:
                state = ProjectState.FAILED
                stages = []
            return PipelineResult(
                project_id=project_id,
                state=state,
                success=False,
                message=f"Pipeline error: {exc}",
                completed_stages=stages,
            )

    def _run_impl(self, project_id: str, request: str) -> PipelineResult:
        """Internal pipeline execution."""
        state = self.workspace.get_state(project_id)
        logger.info(
            "[PipelineSupervisor] pipeline starting from state: %s",
            state.value if hasattr(state, "value") else state,
        )

        # Resume from current state — do not re-run completed phases
        if state in DISCOVERY_STATES:
            result = self._run_discovery(project_id, request)
            if not result.success:
                return result
            # After discovery, check state again (may have paused for design review)
            state = self.workspace.get_state(project_id)
            if state == ProjectState.DESIGN_REVIEW_PENDING:
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=state,
                    success=False,
                    message="Design ready for review",
                    requires_user_action=True,
                    action_needed="review_design",
                    completed_stages=list(data.get("stages_completed", [])),
                )

        if state in SPRINT_STATES or state == ProjectState.DESIGN_APPROVED:
            result = self._run_sprints(project_id, request)
            if not result.success:
                return result
            state = self.workspace.get_state(project_id)

        if state in RELEASE_STATES or state == ProjectState.ALL_SPRINTS_COMPLETE:
            result = self._run_release(project_id, request)
            return result

        # Terminal states
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=state in [ProjectState.DEPLOYABLE, ProjectState.DONE],
            message=f"Pipeline in state: {state.value if hasattr(state, 'value') else state}",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_discovery(self, project_id: str, request: str) -> PipelineResult:
        """Run Discovery phase: requirements, architecture, design.

        Runs stages in order (StrategicReview → ProductOwner → Architect →
        Designer → Security → SprintPlanner → ScrumMaster). Resumes from
        current stage. Pauses for design review after Designer.

        Returns
        -------
        PipelineResult
            success=True if discovery complete, success=False if a stage failed.
            May pause with requires_user_action=True at DESIGN_REVIEW_PENDING.
        """
        logger.info("[PipelineSupervisor] entering Discovery phase")
        data = self.workspace.load_project_json(project_id) or {}
        completed = set(data.get("stages_completed", []))

        for stage_key in get_discovery_stages():
            # Resolve stage name to Stage enum value for completed check
            from .stage_lookup import resolve_stage_name
            stage_value = resolve_stage_name(stage_key)

            if stage_value in completed:
                logger.debug("[PipelineSupervisor] stage %s already completed, skipping", stage_key)
                continue

            logger.debug("[PipelineSupervisor] running discovery stage: %s", stage_key)
            result = self._run_stage_safe(project_id, stage_key, request)
            if not result.success:
                logger.error(
                    "[PipelineSupervisor] discovery stage %s failed: %s",
                    stage_key, result.message,
                )
                return PipelineResult(
                    project_id=project_id,
                    state=self.workspace.get_state(project_id),
                    success=False,
                    message=f"Discovery stage {stage_key} failed: {result.message}",
                    failed_stage=stage_key,
                    completed_stages=list(data.get("stages_completed", [])),
                )

            # After Designer: pause for design review before continuing to Security
            if stage_key == "designer":
                logger.info("[PipelineSupervisor] design ready, pausing for review")
                self.workspace.update_state(project_id, ProjectState.DESIGN_REVIEW_PENDING)
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=ProjectState.DESIGN_REVIEW_PENDING,
                    success=True,
                    message="Design ready for review",
                    requires_user_action=True,
                    action_needed="review_design",
                    completed_stages=list(data.get("stages_completed", [])),
                )

        logger.info("[PipelineSupervisor] Discovery phase complete")
        self.workspace.update_state(project_id, ProjectState.DESIGN_APPROVED)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.DESIGN_APPROVED,
            success=True,
            message="Discovery phase complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_sprints(self, project_id: str, request: str) -> PipelineResult:
        """Run Sprints phase: execute each sprint via SprintSupervisor.

        Loads sprint plan, finds unstarted sprints, runs each one.
        Stops if any sprint returns blocked=True (retry limits exceeded).
        Updates state to ALL_SPRINTS_COMPLETE when all sprints pass.

        Returns
        -------
        PipelineResult
            success=True if all sprints complete.
            success=False + blocked=True if a sprint hits retry limit.
            success=False otherwise.
        """
        logger.info("[PipelineSupervisor] entering Sprints phase")
        data = self.workspace.load_project_json(project_id) or {}
        completed_sprints = set(data.get("completed_sprints", []))

        sprint_plan = self.workspace.get_sprint_plan(project_id)
        if not sprint_plan or not sprint_plan.sprints:
            logger.warning("[PipelineSupervisor] no sprint plan found")
            self.workspace.update_state(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.ALL_SPRINTS_COMPLETE,
                success=True,
                message="No sprints to run",
                completed_stages=list(data.get("stages_completed", [])),
            )

        for sprint in sprint_plan.sprints:
            n = sprint.sprint_number
            if n in completed_sprints:
                logger.debug("[PipelineSupervisor] sprint %d already completed, skipping", n)
                continue

            logger.info("[PipelineSupervisor] running sprint %d", n)
            self.workspace.set_current_sprint(project_id, n)

            sprint_result = self.workflow_manager._run_sprint_with_retry(project_id, sprint, max_attempts=2)

            if not sprint_result.success:
                logger.error(
                    "[PipelineSupervisor] sprint %d failed: %s",
                    n, sprint_result.message,
                )
                return PipelineResult(
                    project_id=project_id,
                    state=self.workspace.get_state(project_id),
                    success=False,
                    message=f"Sprint {n} failed: {sprint_result.message}",
                    failed_stage=f"sprint_{n}",
                    current_sprint=n,
                    completed_stages=list(data.get("stages_completed", [])),
                )

            self.workspace.mark_sprint_complete(project_id, n)
            logger.info("[PipelineSupervisor] sprint %d complete", n)

        logger.info("[PipelineSupervisor] all sprints complete")
        self.workspace.update_state(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.ALL_SPRINTS_COMPLETE,
            success=True,
            message="All sprints complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_release(self, project_id: str, request: str) -> PipelineResult:
        """Run Release phase: QA, DevOps, Documentation, Retro.

        Non-fatal failures: if a stage fails, log WARNING but continue
        (matches current WorkflowManager behavior). All release stages
        run regardless of individual failures. Final state is DEPLOYABLE
        or DONE.

        Returns
        -------
        PipelineResult
            success=True (always succeeds, even if individual stages fail).
        """
        logger.info("[PipelineSupervisor] entering Release phase")

        for stage_key in get_release_stages():
            logger.debug("[PipelineSupervisor] running release stage: %s", stage_key)
            result = self._run_stage_safe(project_id, stage_key, request)
            if not result.success:
                logger.warning(
                    "[PipelineSupervisor] release stage %s failed (non-fatal): %s",
                    stage_key, result.message,
                )
            else:
                logger.info("[PipelineSupervisor] release stage %s complete", stage_key)
                
                if stage_key == "bug_analyst" and hasattr(result, "artifact") and result.artifact:
                    structured = result.artifact.structured_content or {}
                    bug_type = structured.get("type")
                    if bug_type in ("spec_bug", "architecture_bug"):
                        logger.info("[PipelineSupervisor] BugAnalyst detected %s, rolling back pipeline", bug_type)
                        change = self.workflow_manager.submit_requirement_change(
                            project_id=project_id,
                            change_description=f"BugAnalyst detected {bug_type}: {structured.get('fix_instruction')}"
                        )
                        self.workflow_manager.apply_requirement_change(
                            project_id=project_id,
                            change_id=change.change_id,
                            confirmed=True
                        )
                        # State is now RESUMING_FROM_CHANGE, stop release phase so run() restarts discovery
                        return PipelineResult(
                            project_id=project_id,
                            state=ProjectState.RESUMING_FROM_CHANGE,
                            success=True,
                            message=f"Rollback triggered due to {bug_type}",
                            completed_stages=[]
                        )

        logger.info("[PipelineSupervisor] Release phase complete, marking DEPLOYABLE")
        self.workspace.update_state(project_id, ProjectState.DEPLOYABLE)
        data = self.workspace.load_project_json(project_id) or {}
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.DEPLOYABLE,
            success=True,
            message="Release phase complete",
            completed_stages=list(data.get("stages_completed", [])),
        )

    def _run_stage_safe(
        self,
        project_id: str,
        stage_key: str,
        request: str,
    ) -> WorkflowResult | _StageResult:
        """Wrap engine.run() with exception handling."""
        try:
            from .stage_lookup import resolve_stage_name
            resolved_stage = resolve_stage_name(stage_key)
            result: WorkflowResult = self.engine.run(project_id, resolved_stage, request)
            if result.success:
                logger.debug(
                    "[PipelineSupervisor] stage %s succeeded",
                    stage_key,
                )
                return result
            else:
                logger.warning(
                    "[PipelineSupervisor] stage %s failed: %s",
                    stage_key, result.message,
                )
                return result
        except Exception as exc:
            logger.error(
                "[PipelineSupervisor] stage %s raised exception: %s",
                stage_key, exc,
                exc_info=True,
            )
            return _StageResult(
                success=False,
                message=f"{type(exc).__name__}: {exc}",
            )
    # End of PipelineSupervisor

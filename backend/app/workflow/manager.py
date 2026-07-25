from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from ..agents.base_agent import BaseAgent
from ..agents.factory import AgentFactory
from ..artifact.manager import ArtifactManager
from ..execution.project_reader import ProjectReader
from ..execution.project_validator import ProjectValidator, ValidationResult
from ..execution.project_writer import ProjectWriter
from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..shared.enums.stage import Stage
from ..shared.models.sprint import Sprint, SprintResult, SprintStatus
from ..shared.schemas.file_plan_schema import FilePlan
from ..workspace.manager import WorkspaceManager
from .engine import WorkflowEngine
from .execution_state import ExecutionStateRegistry
from .stage_lookup import resolve_stage_name

logger = logging.getLogger(__name__)

# Must match WorkflowEngine._DESIGN_MEMORY_KEY -- the durable slot the approved
# Designer artifact is written to (see workflow/engine.py::_record_design).
_DESIGN_MEMORY_KEY = "design:latest"


class WorkflowManager:
    """State machine orchestrator for AI DevOS.

    Reads current ProjectState -> determines next action -> executes. Every
    state transition is persisted immediately. Crashes are safe: resume from
    last saved state.
    """

    def __init__(
        self,
        engine: WorkflowEngine | None = None,
        workspace_manager: WorkspaceManager | None = None,
        execution_state: ExecutionStateRegistry | None = None,
        agent_factory: AgentFactory | None = None,
        project_validator: ProjectValidator | None = None,
    ) -> None:
        """Wire the engine, workspace_manager, execution_state registry, agent_factory, and project_validator."""
        self.engine = engine or WorkflowEngine()
        self.workspace_manager = workspace_manager or (
            getattr(self.engine, "workspace_manager", None) or WorkspaceManager()
        )
        self.workspace = self.workspace_manager
        self.execution_state = execution_state or ExecutionStateRegistry()
        self._agent_factory = agent_factory or AgentFactory()
        self.project_validator = project_validator or ProjectValidator(self.workspace_manager)
        self.project_writer = ProjectWriter(self.workspace_manager)
        self.artifact_manager = getattr(self.engine, "artifact_manager", None) or ArtifactManager(
            workspace_manager=self.workspace_manager
        )

    def _get_agent(self, stage_name: str) -> BaseAgent:
        """Resolve agent via factory — never instantiate directly."""
        return self._agent_factory.create(stage_name)

    def run(self, project_id: str, request: str = "") -> PipelineResult:
        """Main entry point. Reads current state and advances pipeline.

        Safe to call multiple times — idempotent per state.

        Refuses to start a second pipeline while one is already in flight for
        this project. Each stage blocks on a synchronous LLM call, so without
        this guard every extra POST /workflow/start (a double-click, an
        impatient retry, a component remounting) spawned a *parallel* pipeline
        over the same workspace: duplicate "<stage> started" entries in the
        live log, competing writes to the same project.json and artifacts, and
        one blocked request thread held per run.
        """
        if self.execution_state.is_running(project_id):
            logger.warning("pipeline already running, refusing duplicate start: project_id=%s", project_id)
            data = self.workspace.load_project_json(project_id) or {}
            return PipelineResult(
                project_id=project_id,
                state=self.workspace.get_state(project_id),
                success=False,
                message="A build is already running for this project. Wait for it to finish, or POST /workflow/{id}/stop to cancel it.",
                completed_stages=list(data.get("stages_completed", [])),
            )

        if request:
            self.workspace.update_project_json(project_id, {"original_request": request})
        else:
            p_data = self.workspace.load_project_json(project_id) or {}
            request = p_data.get("original_request") or p_data.get("description") or f"Build project {project_id}"

        while True:
            state = self.workspace.get_state(project_id)

            if state == ProjectState.EMPTY:
                self._transition(project_id, ProjectState.CLARIFYING)

            elif state == ProjectState.CLARIFYING:
                result = self._run_stage(project_id, "StrategicReview", request)
                if result.success:
                    self._transition(project_id, ProjectState.REQUIREMENTS_READY)
                else:
                    return self._fail(project_id, "StrategicReview", result)

            elif state == ProjectState.REQUIREMENTS_READY:
                result = self._run_stage(project_id, "ProductOwner", request)
                if result.success:
                    self._transition(project_id, ProjectState.ARCHITECTURE_READY)
                else:
                    return self._fail(project_id, "Requirements", result)

            elif state == ProjectState.ARCHITECTURE_READY:
                result = self._run_stage(project_id, "Architect", request)
                if result.success:
                    self._transition(project_id, ProjectState.DESIGN_READY)
                else:
                    return self._fail(project_id, "Architecture", result)

            elif state == ProjectState.DESIGN_READY:
                p_data = self.workspace.load_project_json(project_id) or {}
                dr = p_data.get("design_review") or {}
                design_req = request
                if dr.get("status") == "revision_requested":
                    iteration = dr.get("iteration", 2)
                    fb = dr.get("user_feedback") or dr.get("feedback", "")
                    if fb:
                        design_req = (
                            f"{request}\n\n━━━━ USER FEEDBACK ON DESIGN ITERATION {iteration - 1} ━━━━\n"
                            f"{fb}\nYou MUST address every point in this feedback."
                        )

                result = self._run_stage(project_id, "Designer", design_req)
                if result.success:
                    self._transition(project_id, ProjectState.DESIGN_REVIEW_PENDING)
                    data = self.workspace.load_project_json(project_id) or {}
                    completed_stages = list(data.get("stages_completed", []))
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.DESIGN_REVIEW_PENDING,
                        message="Design ready for review",
                        requires_user_action=True,
                        action_needed="review_design",
                        completed_stages=completed_stages,
                    )
                else:
                    return self._fail(project_id, "Design", result)

            elif state == ProjectState.DESIGN_REVIEW_PENDING:
                data = self.workspace.load_project_json(project_id) or {}
                dr = data.get("design_review") or {}
                if dr.get("status") == "approved":
                    self._transition(project_id, ProjectState.DESIGN_APPROVED)
                else:
                    completed_stages = list(data.get("stages_completed", []))
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.DESIGN_REVIEW_PENDING,
                        message="Waiting for design approval",
                        requires_user_action=True,
                        action_needed="review_design",
                        completed_stages=completed_stages,
                    )

            elif state == ProjectState.DESIGN_APPROVED:
                result_sec = self._run_stage(project_id, "Security", request)
                if not result_sec.success:
                    return self._fail(project_id, "Security", result_sec)
                result_fplan = self._run_stage(project_id, "FileStructurePlanner", request)
                if not result_fplan.success:
                    return self._fail(project_id, "FilePlanner", result_fplan)
                result_sp = self._run_stage(project_id, "SprintPlanner", request)
                if result_sp.success:
                    self._transition(project_id, ProjectState.SPRINT_PLAN_READY)
                else:
                    return self._fail(project_id, "SprintPlanning", result_sp)

            elif state == ProjectState.SPRINT_PLAN_READY:
                self._transition(project_id, ProjectState.SPRINT_IN_PROGRESS)

            elif state == ProjectState.SPRINT_IN_PROGRESS:
                result = self._run_next_sprint(project_id)
                if result.all_sprints_complete:
                    self._run_validation_with_healing(project_id, request)
                    self._transition(project_id, ProjectState.ALL_SPRINTS_COMPLETE)
                elif result.sprint_complete:
                    pass
                else:
                    return self._fail(project_id, "Sprint", result)

            elif state == ProjectState.ALL_SPRINTS_COMPLETE:
                result_qa = self._run_stage(project_id, "QA", request)
                logger.info("QA result: %s", result_qa.message)

                result_ops = self._run_stage(project_id, "DevOps", request)
                logger.info("DevOps result: %s", result_ops.message)

                result_doc = self._run_stage(project_id, "Document", request)
                logger.info("Document result: %s", result_doc.message)

                self._transition(project_id, ProjectState.QA_COMPLETE)

            elif state == ProjectState.QA_COMPLETE:
                result_retro = self._run_stage(project_id, "Retro", request)
                if not result_retro.success:
                    return self._fail(project_id, "Retro", result_retro)
                self._transition(project_id, ProjectState.DEPLOYABLE)

            elif state in [
                ProjectState.DEPLOYABLE,
                ProjectState.DONE,
                ProjectState.FAILED,
                ProjectState.PAUSED,
            ]:
                data = self.workspace.load_project_json(project_id) or {}
                completed_stages = list(data.get("stages_completed", []))
                return PipelineResult(
                    project_id=project_id,
                    state=state,
                    success=state in [ProjectState.DEPLOYABLE, ProjectState.DONE],
                    message=f"Pipeline in state: {state.value}",
                    completed_stages=completed_stages,
                )

    def _transition(self, project_id: str, new_state: ProjectState) -> None:
        """Persist state change immediately."""
        self.workspace.update_state(project_id, new_state)
        logger.info("State: %s -> %s", self.workspace.get_state(project_id), new_state)

    def _run_stage(self, project_id: str, stage_name: str, request: str) -> WorkflowResult:
        """Run a stage by name."""
        return self.run_stage(project_id, stage_name, request)

    def _run_next_sprint(self, project_id: str) -> SprintResult:
        """Load sprint plan, find next unstarted sprint, run it."""
        plan = self.workspace.get_sprint_plan(project_id)
        if not plan or not plan.sprints:
            return self._run_default_sprint(project_id)
        for sprint in plan.sprints:
            if sprint.status == SprintStatus.PLANNED:
                return self._run_sprint(project_id, sprint)
        return SprintResult(all_sprints_complete=True)

    def _run_default_sprint(self, project_id: str) -> SprintResult:
        """Fallback sprint when no explicit SprintPlan exists."""
        p_data = self.workspace.load_project_json(project_id) or {}
        request = p_data.get("original_request") or p_data.get("description") or f"Build project {project_id}"
        res_b = self.run_stage(project_id, "BackendDeveloper", request)
        if not res_b.success:
            return SprintResult(sprint_complete=False, success=False, message=res_b.message)
        res_f = self.run_stage(project_id, "FrontendDeveloper", request)
        if not res_f.success:
            return SprintResult(sprint_complete=False, success=False, message=res_f.message)
        return SprintResult(all_sprints_complete=True, sprint_complete=True, success=True)

    def _build_sprint_context(self, project_id: str, sprint: Sprint, arch: object | None) -> str:
        arch_text = getattr(arch, "content", str(arch)) if arch else ""
        return (
            f"Sprint {sprint.sprint_number}: {sprint.name}\n"
            f"Goal: {sprint.goal}\n"
            f"Features: {', '.join(sprint.features)}\n\n"
            f"Architecture Spec:\n{arch_text}"
        )

    def _load_file_plan(self, project_id: str, sprint_number: int) -> FilePlan:
        artifacts_dir = self.workspace_manager.get_workspace_path(project_id) / "artifacts"
        plan_json = artifacts_dir / f"file_plan_sprint_{sprint_number}.json"
        if not plan_json.exists():
            plan_json = artifacts_dir / "FileStructurePlanner.json"
        if not plan_json.exists():
            plan_json = artifacts_dir / "sprint_plan.json"
        if plan_json.exists():
            try:
                data = json.loads(plan_json.read_text(encoding="utf-8"))
                struct = data.get("structured") or data
                return FilePlan.model_validate(struct)
            except Exception as exc:
                logger.warning("Failed to parse file plan json: %s", exc)
        return FilePlan(project_id=project_id, sprint_number=sprint_number)

    def _load_design_artifact(self, project_id: str) -> dict | str | None:
        """Load the design spec to hand to FrontendDeveloper during sprint execution.

        The sprint path calls the code agents directly rather than through
        WorkflowEngine, so WorkflowEngine._with_design_context never runs for
        it -- without this, frontend files were generated with no knowledge of
        the design the user approved, making the design-review gate cosmetic.

        Prefers the user-approved design (post design-review), then the
        engine's durable `design:latest` memory slot, then the raw Designer
        artifact. Returns None when no design exists, in which case the
        frontend prompt is unchanged.
        """
        approved = self.workspace.load_approved_design(project_id)
        if approved:
            return approved

        memory_manager = getattr(self.engine, "memory_manager", None)
        if memory_manager is not None:
            raw = memory_manager.load(project_id, _DESIGN_MEMORY_KEY)
            if raw:
                try:
                    return json.loads(raw)
                except (ValueError, TypeError):
                    return raw

        artifact = self.artifact_manager.get_artifact(project_id, Stage.Designer)
        if artifact is not None:
            return getattr(artifact, "structured_content", None) or artifact.content or None
        return None

    def _run_sprint(self, project_id: str, sprint: Sprint) -> SprintResult:
        """Run one complete sprint:
        1. FilePlannerAgent creates file_plan.json
        2. BackendDeveloper generates backend files
        3. FrontendDeveloper generates frontend files
        4. Mark sprint complete
        """
        logger.info("Starting sprint %d: %s", sprint.sprint_number, sprint.name)
        self.workspace.set_current_sprint(project_id, sprint.sprint_number)

        arch = self.artifact_manager.get_artifact(project_id, Stage.Architect)
        plan_context = self._build_sprint_context(project_id, sprint, arch)
        plan_result = self._run_stage(project_id, "file_planner", plan_context)

        if not plan_result.success:
            return SprintResult(success=False, message=plan_result.message)

        file_plan = self._load_file_plan(project_id, sprint.sprint_number)

        if sprint.sprint_number == 1:
            tech_stack = getattr(file_plan, "tech_stack", {}) or {}
            self.project_writer.initialize_project(project_id, tech_stack)

        context_obj = SimpleNamespace(project_id=project_id)
        backend_result = self._get_agent("backend").execute_sprint(
            project_id=project_id,
            file_plan=file_plan,
            context=context_obj,
        )

        frontend_result = self._get_agent("frontend").execute_sprint(
            project_id=project_id,
            file_plan=file_plan,
            context=context_obj,
            design_artifact=self._load_design_artifact(project_id),
        )

        all_success = bool(backend_result.success and frontend_result.success)
        if all_success:
            self.workspace.mark_sprint_complete(project_id, sprint.sprint_number)

        return SprintResult(
            sprint_complete=all_success,
            all_sprints_complete=False,
            success=all_success,
            message="Sprint completed" if all_success else "Sprint execution failed",
        )

    def _fail(self, project_id: str, stage_label: str, result: WorkflowResult | SprintResult) -> PipelineResult:
        """Handle failure in a stage or sprint."""
        self._transition(project_id, ProjectState.FAILED)
        self.workspace.update_project_json(project_id, {"failed_at_stage": stage_label, "failure_reason": result.message})
        data = self.workspace.load_project_json(project_id) or {}
        completed = list(data.get("stages_completed", []))
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.FAILED,
            success=False,
            message=f"Pipeline failed at {stage_label}: {result.message}",
            failed_stage=stage_label,
            completed_stages=completed,
        )

    def run_stage(self, project_id: str, stage_name: str, content: str) -> WorkflowResult:
        """Run stage_name with content for project_id through the WorkflowEngine."""
        stage_name = resolve_stage_name(stage_name)
        logger.info("workflow manager running: project_id=%s stage=%s", project_id, stage_name)
        self.execution_state.mark_running(project_id)
        self.workspace_manager.update_project_json(project_id, {"stopped": False})
        try:
            result = self.engine.run(project_id, stage_name, content)
        finally:
            self.execution_state.mark_stopped(project_id)
        if result.stopped:
            self.workspace_manager.update_project_json(project_id, {"stopped": True})
        return result

    def _run_validation_with_healing(
        self,
        project_id: str,
        original_request: str,
        max_healing_attempts: int = 3,
    ) -> ValidationResult:
        """Validate the generated project. If startup fails, feed the error to BackendDeveloperAgent
        for a targeted fix. Repeat up to max_healing_attempts times.
        """
        result = self.project_validator.validate(project_id)
        for attempt in range(1, max_healing_attempts + 1):
            logger.info("Validation attempt %d/%d for project %s", attempt, max_healing_attempts, project_id)
            result = self.project_validator.validate(project_id)
            if result.passed:
                logger.info("Validation PASSED on attempt %d for %s", attempt, project_id)
                return result

            if attempt < max_healing_attempts and result.fixable_errors:
                error_context = (
                    f"The generated project failed validation (attempt {attempt}/{max_healing_attempts}).\n\n"
                    f"Errors that need to be fixed:\n"
                    + "\n".join(f"  - {e}" for e in result.fixable_errors[:5])
                    + "\n\nFix ONLY the files mentioned in these errors. Do not rewrite other files."
                )
                logger.warning(
                    "Validation failed — running self-healing for %s: %s",
                    project_id, error_context[:200]
                )
                self.run_stage(project_id=project_id, stage_name="backend", content=error_context)
            else:
                logger.error("Validation failed after %d attempts for %s", attempt, project_id)
                break

        return result

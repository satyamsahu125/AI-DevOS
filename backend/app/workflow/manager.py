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
        impact_analyzer: Any | None = None,
        container: Any | None = None,
    ) -> None:
        """Wire the engine, workspace_manager, execution_state registry, agent_factory, project_validator, and DI container.

        ``container`` must be the live DI Container so that _run_sprint() can resolve
        ``backend_developer_agent`` and ``frontend_developer_agent`` via the container
        instead of bypassing DI by instantiating them through AgentFactory directly.
        When None (unit-test paths), _run_sprint falls back to AgentFactory.
        """
        self.engine = engine or WorkflowEngine()
        self.workspace_manager = workspace_manager or (
            getattr(self.engine, "workspace_manager", None) or WorkspaceManager()
        )
        self.workspace = self.workspace_manager
        self.execution_state = execution_state or ExecutionStateRegistry()
        self._agent_factory = agent_factory or AgentFactory()
        self._container = container  # None in unit tests — _run_sprint falls back to factory
        self.project_validator = project_validator or ProjectValidator(self.workspace_manager)
        self.project_writer = ProjectWriter(self.workspace_manager)
        self.artifact_manager = getattr(self.engine, "artifact_manager", None) or ArtifactManager(
            workspace_manager=self.workspace_manager
        )
        if impact_analyzer is not None:
            self.impact_analyzer = impact_analyzer
        else:
            from .impact_analyzer import ImpactAnalyzer
            self.impact_analyzer = ImpactAnalyzer(
                llm_manager=getattr(self.engine, "llm_manager", None),
                artifact_manager=self.artifact_manager,
            )
        self.broadcaster = getattr(self.engine, "broadcaster", None)
        if self.broadcaster is None:
            from ..events.broadcaster import broadcaster as default_broadcaster
            self.broadcaster = default_broadcaster

    def _get_agent(self, stage_name: str) -> BaseAgent:
        """Resolve agent via factory — never instantiate directly."""
        return self._agent_factory.create(stage_name)

    def _sanitize_stages_completed(
        self,
        stages_completed: list[str],
        stage_order: list[Stage],
    ) -> list[str]:
        """Remove any stage from stages_completed that comes after
        a stage that is NOT in stages_completed.
        Prevents gaps where stage 5 is "complete" but stage 4 is not.
        """
        order = [s.value for s in stage_order]
        clean = []
        for stage in order:
            if stage in stages_completed:
                clean.append(stage)
            else:
                break  # first incomplete stage found — stop
        return clean

    def run(self, project_id: str, request: str = "", skip_qa: bool = False) -> PipelineResult:
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
        if not project_id:
            return PipelineResult(
                project_id="",
                state=ProjectState.FAILED,
                success=False,
                message="project_id is required and cannot be empty",
                completed_stages=[],
            )

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

        p_data = self.workspace.load_project_json(project_id) or {}
        if request:
            self.workspace.update_project_json(project_id, {"original_request": request})
        else:
            request = p_data.get("original_request") or p_data.get("description") or f"Build project {project_id}"

        from .dependency_graph import DependencyGraph
        raw_completed = p_data.get("stages_completed", [])
        stages_completed = self._sanitize_stages_completed(
            raw_completed, DependencyGraph.ordered_stages()
        )
        if raw_completed != stages_completed:
            logger.warning(
                "Sanitized stages_completed for %s: %s → %s (removed gap stages)",
                project_id, raw_completed, stages_completed
            )
            self.workspace.update_project_json(
                project_id, {"stages_completed": stages_completed}
            )

        while True:
            state = self.workspace.get_state(project_id)

            if state == ProjectState.EMPTY:
                self._transition(project_id, ProjectState.CLARIFYING)

            elif state == ProjectState.CLARIFYING:
                if skip_qa:
                    result = self._run_stage(project_id, "StrategicReview", request)
                    if result.success:
                        self._transition(project_id, ProjectState.REQUIREMENTS_READY)
                    else:
                        return self._fail(project_id, "StrategicReview", result)
                else:
                    from ..agents.clarification import ClarificationAgent
                    agent = self._get_agent("clarification")
                    if isinstance(agent, ClarificationAgent):
                        q_set = agent.generate_questions(request)
                        questions = [q.model_dump(mode="json") if hasattr(q, "model_dump") else q for q in q_set.questions]
                    else:
                        questions = []
                    if questions:
                        self.workspace.save_qa_questions(project_id, questions)
                        self._transition(project_id, ProjectState.QA_PENDING)
                        data = self.workspace.load_project_json(project_id) or {}
                        completed_stages = list(data.get("stages_completed", []))
                        return PipelineResult(
                            project_id=project_id,
                            state=ProjectState.QA_PENDING,
                            requires_user_action=True,
                            action_needed="answer_questions",
                            message=f"I have {len(questions)} questions to help me understand your project better.",
                            completed_stages=completed_stages,
                        )
                    else:
                        result = self._run_stage(project_id, "StrategicReview", request)
                        if result.success:
                            self._transition(project_id, ProjectState.REQUIREMENTS_READY)
                        else:
                            return self._fail(project_id, "StrategicReview", result)

            elif state == ProjectState.QA_PENDING:
                qa = self.workspace.get_qa_session(project_id)
                answered = len(qa.get("answers", []))
                total = len(qa.get("questions", []))
                if total > 0 and answered < total:
                    data = self.workspace.load_project_json(project_id) or {}
                    completed_stages = list(data.get("stages_completed", []))
                    return PipelineResult(
                        project_id=project_id,
                        state=ProjectState.QA_PENDING,
                        requires_user_action=True,
                        action_needed="answer_questions",
                        message=f"Answered {answered}/{total} questions. Please answer remaining questions.",
                        completed_stages=completed_stages,
                    )
                else:
                    self._transition(project_id, ProjectState.QA_IN_PROGRESS)

            elif state == ProjectState.QA_IN_PROGRESS:
                from ..agents.clarification import ClarificationAgent
                agent = self._get_agent("clarification")
                qa = self.workspace.get_qa_session(project_id)
                if isinstance(agent, ClarificationAgent):
                    artifact_obj = agent.process_answers(request, qa)
                    struct = artifact_obj.model_dump(mode="json") if hasattr(artifact_obj, "model_dump") else {}
                    content_str = getattr(artifact_obj, "clarified_requirement", "") or request
                    self.artifact_manager.save_artifact(
                        project_id=project_id,
                        stage=Stage.StrategicReview,
                        content=content_str,
                        structured_content=struct,
                    )
                self.workspace.mark_qa_complete(project_id)
                self._transition(project_id, ProjectState.REQUIREMENTS_READY)


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

                result_sp = self._run_stage(project_id, "SprintPlanner", request)
                if not result_sp.success:
                    return self._fail(project_id, "SprintPlanning", result_sp)
                self._handle_sprint_planner_approval(project_id, result_sp)

                result_sm = self._run_stage(project_id, "ScrumMaster", request)
                if not result_sm.success:
                    return self._fail(project_id, "ScrumMaster", result_sm)

                # FileStructurePlanner runs per-sprint inside _run_sprint() so it
                # has access to the per-sprint context (goal, features, tasks).
                # Running it here globally (before any sprint starts) meant it had
                # no sprint context and its output was immediately overwritten on
                # the first sprint anyway — a pure duplicate that wasted one LLM call.
                self._transition(project_id, ProjectState.SPRINT_PLAN_READY)

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

            elif state == ProjectState.CHANGE_REQUESTED:
                # Waiting for the user to confirm or cancel via apply_requirement_change().
                # Do NOT advance automatically — return and let the API caller decide.
                data = self.workspace.load_project_json(project_id) or {}
                pending = data.get("pending_change") or {}
                completed_stages = list(data.get("stages_completed", []))
                return PipelineResult(
                    project_id=project_id,
                    state=ProjectState.CHANGE_REQUESTED,
                    requires_user_action=True,
                    action_needed="confirm_change",
                    message=(
                        f"Requirement change pending — confirm or cancel to resume. "
                        f"Change: {pending.get('description', '(no description)')}"
                    ),
                    completed_stages=completed_stages,
                )

            elif state == ProjectState.RESUMING_FROM_CHANGE:
                from datetime import datetime, timezone
                pj = self.workspace.load_project_json(project_id) or {}
                changes = pj.get("requirement_changes", [])
                last_change = changes[-1] if changes else None

                enriched_request = request
                if last_change:
                    enriched_request = (
                        f"{request}\n\n"
                        f"REQUIREMENT CHANGE APPLIED:\n"
                        f"{last_change.get('description', '')}\n"
                        + (f"Additional context: {last_change.get('comment')}"
                           if last_change.get('comment') else "")
                    )
                    request = enriched_request

                self._transition(project_id, ProjectState.SPRINT_IN_PROGRESS)

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

            else:
                # Safety catch: any state not handled above (IMPACT_ANALYZED, REPLANNING,
                # SPRINT_COMPLETE, AWAITING_HUMAN_APPROVAL, or any future additions)
                # must not spin forever in this loop.
                logger.error(
                    "WorkflowManager.run(): unhandled state '%s' for project '%s' — halting pipeline",
                    state, project_id,
                )
                data = self.workspace.load_project_json(project_id) or {}
                return PipelineResult(
                    project_id=project_id,
                    state=state,
                    success=False,
                    message=(
                        f"Unhandled pipeline state: "
                        f"{state.value if hasattr(state, 'value') else state}"
                    ),
                    completed_stages=list(data.get("stages_completed", [])),
                )

    def submit_requirement_change(
        self,
        project_id: str,
        change_description: str,
    ):
        """User submits a requirement change.

        Analyzes impact and returns which stages will re-run.
        Does NOT start re-running yet — waits for confirmation.
        """
        pj = self.workspace.load_project_json(project_id) or {}
        stages_completed = pj.get("stages_completed", [])

        analysis = self.impact_analyzer.analyze(
            project_id=project_id,
            change_description=change_description,
            stages_completed=stages_completed,
        )

        self.workspace.update_project_json(project_id, {
            "pending_change": {
                "change_id": analysis.change_id,
                "description": change_description,
                "affected_stages": analysis.affected_stages,
                "safe_stages": analysis.safe_stages,
                "analyzed_at": analysis.analyzed_at.isoformat(),
            }
        })

        self._transition(project_id, ProjectState.CHANGE_REQUESTED)
        self.broadcaster.change_analyzed(
            project_id=project_id,
            affected_stages=analysis.affected_stages,
            safe_stages=analysis.safe_stages,
        )
        logger.info(
            "Requirement change submitted for %s: %s affected stages",
            project_id, len(analysis.affected_stages)
        )
        return analysis

    def apply_requirement_change(
        self,
        project_id: str,
        change_id: str,
        confirmed: bool,
        user_comment: str = "",
    ) -> dict:
        """User confirmed they want to apply the change.

        Removes affected stages from stages_completed.
        Pipeline resumes from the first affected stage.
        """
        from datetime import datetime, timezone

        if not confirmed:
            self.workspace.update_project_json(project_id, {
                "pending_change": None
            })
            self._transition(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return {"status": "cancelled"}

        pj = self.workspace.load_project_json(project_id) or {}
        pending = pj.get("pending_change", {})

        if pending.get("change_id") != change_id:
            raise ValueError(f"Change ID mismatch: {change_id}")

        affected = pending.get("affected_stages", [])
        safe_stages = pending.get("safe_stages", [])

        changes = pj.get("requirement_changes", [])
        changes.append({
            "change_id": change_id,
            "description": pending.get("description", ""),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "comment": user_comment,
            "stages_rerun": affected,
        })

        self.workspace.update_project_json(project_id, {
            "stages_completed": safe_stages,
            "pending_change": None,
            "requirement_changes": changes,
            "current_stage": affected[0] if affected else None,
        })

        self._transition(project_id, ProjectState.RESUMING_FROM_CHANGE)

        logger.info(
            "Requirement change applied for %s. "
            "Removed %d stages. Resuming from %s.",
            project_id, len(affected),
            affected[0] if affected else "end"
        )

        return {
            "status": "applied",
            "stages_removed": affected,
            "stages_kept": safe_stages,
            "resuming_from": affected[0] if affected else None,
        }

    def _transition(self, project_id: str, new_state: ProjectState) -> None:
        """Persist state change immediately."""
        self.workspace.update_state(project_id, new_state)
        logger.info("State: %s -> %s", self.workspace.get_state(project_id), new_state)
        data = self.workspace.load_project_json(project_id) or {}
        st_val = new_state.value if hasattr(new_state, "value") else str(new_state)
        self.broadcaster.status_update(
            project_id=project_id,
            state=st_val,
            current_stage=data.get("current_stage"),
            stages_completed=data.get("stages_completed", []),
        )

    def _run_stage(self, project_id: str, stage_name: str, request: str) -> WorkflowResult:
        """Run a stage by name."""
        return self.run_stage(project_id, stage_name, request)

    def _run_next_sprint(self, project_id: str) -> SprintResult:
        """Load sprint plan, find next unstarted sprint, run it with up to 2 attempts."""
        plan = self.workspace.get_sprint_plan(project_id)
        if not plan or not plan.sprints:
            return self._run_default_sprint(project_id)
        for sprint in plan.sprints:
            if sprint.status == SprintStatus.PLANNED:
                return self._run_sprint_with_retry(project_id, sprint, max_attempts=2)
        return SprintResult(all_sprints_complete=True)

    def _run_sprint_with_retry(self, project_id: str, sprint: Sprint, max_attempts: int = 2) -> SprintResult:
        """Run a sprint, retrying once on failure before giving up.

        Sprint-level retry is distinct from stage-level retry (WorkflowEngine.run()
        retries each LLM call up to RetryPolicy.max_retries times). This adds a
        coarser outer retry: if the whole sprint (file plan + backend + frontend)
        fails, we try the entire sprint once more before reporting failure.
        This handles transient execution errors (e.g. file write race, LLM timeout)
        that are unlikely to repeat on a second full attempt.
        """
        last_result: SprintResult | None = None
        for attempt in range(1, max_attempts + 1):
            last_result = self._run_sprint(project_id, sprint)
            if last_result.sprint_complete:
                if attempt > 1:
                    logger.info(
                        "Sprint %d succeeded on retry attempt %d/%d for %s",
                        sprint.sprint_number, attempt, max_attempts, project_id,
                    )
                return last_result
            logger.warning(
                "Sprint %d attempt %d/%d failed for %s: %s",
                sprint.sprint_number, attempt, max_attempts, project_id, last_result.message,
            )
        return last_result or SprintResult(
            sprint_complete=False, success=False,
            message=f"Sprint {sprint.sprint_number} failed after {max_attempts} attempts",
        )

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
        """Build the context string passed to developer agents for this sprint.

        Injects Architecture spec AND the approved ScrumMaster plan so that
        developer agents know sprint ceremonies, velocity targets, and team
        assignments — not just the raw architecture. Without ScrumMaster context
        the sprint execution effectively ignores the Agile planning layer.
        """
        arch_text = getattr(arch, "content", str(arch)) if arch else ""

        scrum_artifact = self.artifact_manager.get_artifact(project_id, Stage.ScrumMaster)
        scrum_text = getattr(scrum_artifact, "content", "") if scrum_artifact else ""

        parts = [
            f"Sprint {sprint.sprint_number}: {sprint.name}",
            f"Goal: {sprint.goal}",
            f"Features: {', '.join(sprint.features)}",
            "",
            f"Architecture Spec:\n{arch_text}",
        ]
        if scrum_text:
            parts.append(f"\nScrumMaster Plan:\n{scrum_text[:2000]}")

        return "\n".join(parts)

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

        # Resolve developers from the DI container so they get their properly-wired
        # singletons (llm_manager, project_writer, validator, workspace_manager).
        # Fall back to AgentFactory only in unit-test paths where container is None.
        if self._container is not None:
            backend_agent = self._container.resolve("backend_developer_agent")
            frontend_agent = self._container.resolve("frontend_developer_agent")
        else:
            backend_agent = self._get_agent("backend")
            frontend_agent = self._get_agent("frontend")

        backend_result = backend_agent.execute_sprint(
            project_id=project_id,
            file_plan=file_plan,
            context=context_obj,
        )

        frontend_result = frontend_agent.execute_sprint(
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

    def _handle_sprint_planner_approval(
        self,
        project_id: str,
        result: WorkflowResult,
    ) -> None:
        """Save approved sprint plan to project.json."""
        artifact = self.artifact_manager.get_artifact(project_id, Stage.SprintPlanning)
        if artifact and artifact.structured_content:
            self.workspace.update_project_json(
                project_id,
                {"sprint_plan": artifact.structured_content},
            )
            sprint_count = len(artifact.structured_content.get("sprints", []))
            logger.info("Sprint plan saved for %s: %d sprints", project_id, sprint_count)

    def _run_validation_with_healing(
        self,
        project_id: str,
        original_request: str,
        max_healing_attempts: int = 3,
    ) -> ValidationResult:
        """Validate the generated project. If startup fails, feed the error to BackendDeveloperAgent
        for a targeted fix. Repeat up to max_healing_attempts times.
        """
        result = None
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

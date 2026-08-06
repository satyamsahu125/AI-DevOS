from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from typing import Any

from ..agents.base_agent import BaseAgent
from ..agents.factory import AgentFactory
from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..execution.project_reader import ProjectReader
from ..execution.project_validator import ProjectValidator, ValidationResult
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..shared.enums.stage import Stage
from ..shared.models.sprint import Sprint, SprintResult, SprintStatus
from ..shared.schemas.file_plan_schema import FilePlan
from ..workspace.manager import WorkspaceManager
from .engine import WorkflowEngine
from .execution_state import ExecutionStateRegistry
from .pipeline_supervisor import PipelineSupervisor
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
        sprint_monitor: Any | None = None,
        domain_researcher: Any | None = None,
        config_manager: ConfigurationManager | None = None,
        file_indexer: Any | None = None,
        code_sandbox: Any | None = None,
        dependency_pinner: Any | None = None,
        preview_manager: Any | None = None,
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
        self.sprint_monitor = sprint_monitor   # None = feature disabled
        self.domain_researcher = domain_researcher  # None = feature disabled

        # Wire up Phase 3: PipelineSupervisor and SprintSupervisor
        config_mgr = config_manager or ConfigurationManager()
        self._settings = config_mgr.load() if hasattr(config_mgr, "load") else getattr(config_mgr, "settings", lambda: getattr(config_mgr, "_settings", None))()
        if not self._settings and hasattr(config_mgr, "load"):
             self._settings = config_mgr.load()
        self._sprint_retry = getattr(self._settings, "sprint_retry", None)
        self._llm_manager = getattr(self.engine, "llm_manager", None) or LLMManager()
        self._pipeline_supervisor = PipelineSupervisor(
            workspace=self.workspace_manager,
            engine=self.engine,
            workflow_manager=self,
            settings=self._settings,
            file_indexer=file_indexer,           # Phase 3: intelligence indexing trigger
            code_sandbox=code_sandbox,           # Phase 5: code execution sandbox
            dependency_pinner=dependency_pinner,  # R2: pin requirements to stable versions
            preview_manager=preview_manager,      # R5: live app preview
        )

    def _get_agent(self, stage_name: str) -> BaseAgent:
        """Resolve agent via factory — never instantiate directly."""
        return self._agent_factory.create(stage_name)

    # Stages that are *implied* by each ProjectState reaching that state means
    # every stage in the tuple definitely ran (even via the Q&A bypass path).
    _STATE_IMPLIED_STAGES: dict[str, tuple[str, ...]] = {
        # past REQUIREMENTS_READY → StrategicReview processed via Q&A or directly
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

    def _sanitize_stages_completed(
        self,
        stages_completed: list[str],
        stage_order: list[Stage],
        current_state: str = "",
    ) -> list[str]:
        """Return a prefix of stage_order that is fully contiguous in stages_completed.

        Also injects any stages *implied* by the current pipeline state before
        running the prefix check.  This prevents the gap-sanitizer from wiping
        valid stages on projects that ran before FIX-2 (which adds StrategicReview
        to stages_completed in the Q&A path) or whose project.json was corrupted
        and repaired.
        """
        # Merge in any stages implied by where the pipeline currently sits.
        implied = self._STATE_IMPLIED_STAGES.get(current_state, ())
        merged = list(stages_completed)
        for s in implied:
            if s not in merged:
                merged.append(s)

        order = [s.value for s in stage_order]
        clean = []
        for stage in order:
            if stage in merged:
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

        Uses PipelineSupervisor (Phase 3) to orchestrate the 3-phase pipeline
        (Discovery → Sprints → Release). Delegates to the old state machine
        only for CLARIFYING state to maintain Q&A flow compatibility.
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
        current_state_str = p_data.get("state", "")
        stages_completed = self._sanitize_stages_completed(
            raw_completed, DependencyGraph.ordered_stages(), current_state=current_state_str
        )
        if raw_completed != stages_completed:
            logger.warning(
                "Sanitized stages_completed for %s: %s → %s (implied by state=%s)",
                project_id, raw_completed, stages_completed, current_state_str,
            )
            self.workspace.update_project_json(
                project_id, {"stages_completed": stages_completed}
            )

        state = self.workspace.get_state(project_id)

        # Mark running for the duration of this workflow invocation (including Clarifying/QA)
        self.execution_state.mark_running(project_id)
        self.workspace.update_project_json(project_id, {"stopped": False})
        try:
            # EMPTY = brand-new project; enter Q&A flow before running any agent.
            # ProjectInitializer sets CLARIFYING; this guard covers cases where the
            # workspace was created without calling ProjectInitializer (e.g. tests,
            # direct workspace creation) and state was never advanced past EMPTY.
            if state == ProjectState.EMPTY:
                self._transition(project_id, ProjectState.CLARIFYING)
                state = ProjectState.CLARIFYING

            # Handle CLARIFYING state: domain research → Q&A question generation
            if state == ProjectState.CLARIFYING:
                return self._handle_clarifying_state(project_id, request, skip_qa)

            # Handle Q&A states (pre-discovery)
            if state in [ProjectState.QA_PENDING, ProjectState.QA_IN_PROGRESS]:
                return self._handle_qa_flow(project_id, request)

            # Phase 4: Human collaboration gate states — return pause result.
            # Resumption happens via POST /workflow/{id}/gates/{gate}/approve.
            if state == ProjectState.ARCHITECTURE_REVIEW_PENDING:
                return self._await_gate(project_id, "architecture")
            if state == ProjectState.DESIGN_REVIEW_PENDING:
                return self._await_gate(project_id, "design")
            if state == ProjectState.SPRINT_PLAN_REVIEW_PENDING:
                return self._await_gate(project_id, "sprint_plan")

            # For all other states, use PipelineSupervisor (Phase 3)
            return self._pipeline_supervisor.run(project_id, request)
        finally:
            self.execution_state.mark_stopped(project_id)

    def _handle_clarifying_state(
        self, project_id: str, request: str, skip_qa: bool
    ) -> PipelineResult:
        """Handle CLARIFYING state Q&A flow (retained for backwards compatibility).

        This is kept separate from PipelineSupervisor to maintain the existing Q&A
        user interaction pattern. Once CLARIFYING completes (via Q&A or skip_qa),
        control passes to PipelineSupervisor for the rest of the pipeline.
        """
        if skip_qa:
            result = self._run_stage(project_id, "StrategicReview", request)
            if result.success:
                self._transition(project_id, ProjectState.REQUIREMENTS_READY)
                # Continue pipeline via PipelineSupervisor
                return self._pipeline_supervisor.run(project_id, request)
            else:
                return self._fail(project_id, "StrategicReview", result)
        else:
            from ..agents.clarification import ClarificationAgent
            
            # Retry loop for initial domain research and Q&A generation to handle LLM flakiness
            max_retries = 3
            questions = []
            for attempt in range(max_retries):
                try:
                    self.broadcaster.status_update(
                        project_id=project_id,
                        state=ProjectState.CLARIFYING.value,
                        current_stage="Clarifying"
                    )
                    self.broadcaster.log_line(project_id, "DomainResearch", f"Attempt {attempt+1}/{max_retries}: Running domain research...")
                    # Run domain research BEFORE generating questions so Q&A is domain-aware
                    domain_brief = self._run_domain_research(project_id, request)
                    self.broadcaster.log_line(project_id, "Clarifying", f"Attempt {attempt+1}/{max_retries}: Generating clarification questions...")
                    agent = self._get_agent("clarification")
                    if isinstance(agent, ClarificationAgent):
                        q_set = agent.generate_questions(request, domain_brief=domain_brief)
                        questions = [q.model_dump(mode="json") if hasattr(q, "model_dump") else q for q in q_set.questions]
                        if questions:
                            break  # Success!
                except Exception as exc:
                    logger.warning("Clarification generation failed on attempt %d: %s", attempt + 1, exc)
                    if attempt == max_retries - 1:
                        # On final failure, mark project as FAILED so user sees it in the UI
                        return self._fail(
                            project_id, "Clarifying",
                            SimpleNamespace(message=f"Failed to generate clarification questions: {exc}")
                        )
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
                # Bug A fix: question generation returned empty list — QA bypassed silently.
                # Save a minimal Clarification artifact so ProductOwner always has context.
                logger.warning(
                    "QA bypassed for %s: question generation returned empty list. "
                    "Saving minimal clarification artifact and proceeding without Q&A.",
                    project_id,
                )
                import json as _json_bugA
                minimal_clarification = {
                    "original_request": request,
                    "project_description": request,
                    "functional_requirements": [],
                    "non_functional_requirements": [],
                    "scale_profile": {
                        "user_count": "unknown",
                        "auth_needed": False,
                        "database_needed": False,
                        "infrastructure_tier": "unknown",
                    },
                    "explicit_non_requirements": [],
                    "open_questions": [],
                    "inferred_scope": (
                        "QA was bypassed — question generation returned no questions. "
                        "Infer full scope from the original request only."
                    ),
                }
                self.artifact_manager.save_artifact(
                    project_id=project_id,
                    stage=Stage.Clarification,
                    content=_json_bugA.dumps(minimal_clarification, indent=2),
                    structured_content=minimal_clarification,
                )
                # Phase 1: write to per-stage episodic memory so MemoryOrchestrator
                # can read it during ProductOwner context assembly.
                _mo = getattr(getattr(self, "engine", None), "memory_orchestrator", None)
                if _mo is not None:
                    _mo.record_approval(project_id, Stage.Clarification, minimal_clarification)
                else:
                    _mm = getattr(getattr(self, "engine", None), "memory_manager", None)
                    if _mm is not None:
                        _mm.store_stage_output(project_id, Stage.Clarification.value, _json_bugA.dumps(minimal_clarification, indent=2))
                result = self._run_stage(project_id, "StrategicReview", request)
                if result.success:
                    self._transition(project_id, ProjectState.REQUIREMENTS_READY)
                    # Continue pipeline via PipelineSupervisor
                    return self._pipeline_supervisor.run(project_id, request)
                else:
                    return self._fail(project_id, "StrategicReview", result)

    def _handle_qa_flow(self, project_id: str, request: str) -> PipelineResult:
        """Handle Q&A states (QA_PENDING, QA_IN_PROGRESS).

        Once Q&A completes, transitions to REQUIREMENTS_READY and continues
        the pipeline via PipelineSupervisor.
        """
        state = self.workspace.get_state(project_id)

        if state == ProjectState.QA_PENDING:
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
                state = ProjectState.QA_IN_PROGRESS  # update local variable so next block fires

        if state == ProjectState.QA_IN_PROGRESS:
            self.broadcaster.status_update(
                project_id=project_id,
                state=ProjectState.QA_IN_PROGRESS.value,
                current_stage="Synthesizing Requirements"
            )
            self.broadcaster.log_line(project_id, "Clarifying", "Synthesizing requirements from Q&A session...")
            
            from ..agents.clarification import ClarificationAgent
            agent = self._get_agent("clarification")
            qa = self.workspace.get_qa_session(project_id)

            # ── Phase B: synthesise Q&A answers into ClarificationArtifact ──────
            clarification_struct: dict = {}
            if isinstance(agent, ClarificationAgent):
                artifact_obj = agent.process_answers(request, qa)
                clarification_struct = (
                    artifact_obj.model_dump(mode="json")
                    if hasattr(artifact_obj, "model_dump") else {}
                )

            # Save ClarificationArtifact to Stage.Clarification (NOT StrategicReview).
            # ProductOwner's predecessor chain reads Stage.StrategicReview for the
            # StrategicBrief — storing Q&A output there caused ProductOwner to treat
            # Q&A answers as a StrategicBrief, producing an empty/error artifact.
            import json as _json
            self.artifact_manager.save_artifact(
                project_id=project_id,
                stage=Stage.Clarification,
                content=_json.dumps(clarification_struct, indent=2),
                structured_content=clarification_struct,
            )
            # Phase 1: write to per-stage episodic memory so MemoryOrchestrator
            # can load this during ProductOwner context assembly.
            _mo = getattr(getattr(self, "engine", None), "memory_orchestrator", None)
            if _mo is not None:
                _mo.record_approval(project_id, Stage.Clarification, clarification_struct)
            else:
                _mm = getattr(getattr(self, "engine", None), "memory_manager", None)
                if _mm is not None:
                    _mm.store_stage_output(project_id, Stage.Clarification.value, _json.dumps(clarification_struct, indent=2))
            self.workspace.mark_qa_complete(project_id)

            # ── Phase C: run StrategicReview as a real LLM stage ─────────────────
            # Build an agent-readable JSON context: ClarificationArtifact +
            # DomainResearch brief.  StrategicReview produces a StrategicBrief
            # from this, giving ProductOwner a meaningful predecessor artifact.
            domain_artifact = self.artifact_manager.get_artifact(project_id, Stage.DomainResearch)
            domain_struct = (
                getattr(domain_artifact, "structured_content", None) or {}
                if domain_artifact else {}
            )
            strategic_context = _json.dumps({
                "original_request": request,
                "clarification": clarification_struct,
                "domain_research": domain_struct,
            }, indent=2)

            strategic_result = self._run_stage(project_id, "StrategicReview", strategic_context)
            if not strategic_result.success:
                logger.warning(
                    "StrategicReview failed after Q&A for %s: %s — continuing anyway",
                    project_id, strategic_result.message,
                )

            # Ensure stages_completed has a contiguous prefix including both
            # Clarification and StrategicReview so the gap-sanitizer never wipes them.
            _qa_data = self.workspace.load_project_json(project_id) or {}
            _completed = list(_qa_data.get("stages_completed", []))
            for _stage_val in (Stage.Clarification.value, Stage.StrategicReview.value):
                if _stage_val not in _completed:
                    _completed.insert(0, _stage_val)
            self.workspace.update_project_json(project_id, {"stages_completed": _completed})

            self._transition(project_id, ProjectState.REQUIREMENTS_READY)
            # Continue pipeline via PipelineSupervisor (ProductOwner → Architect → …)
            self.execution_state.mark_running(project_id)
            self.workspace.update_project_json(project_id, {"stopped": False})
            try:
                return self._pipeline_supervisor.run(project_id, request)
            finally:
                self.execution_state.mark_stopped(project_id)

        # Shouldn't reach here
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=False,
            message="Unexpected state in QA flow",
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

        # FIX 4: Use file-level impact analysis when code files already exist
        code_stages = {"backend", "frontend", "BackendDeveloper", "FrontendDeveloper"}
        use_file_level = any(s in code_stages for s in stages_completed)
        if use_file_level and hasattr(self.impact_analyzer, "analyze_file_impact"):
            file_impact = self.impact_analyzer.analyze_file_impact(
                project_id=project_id,
                change_description=change_description,
            )
            logger.info(
                "File-level impact analysis for %s: %d files affected, %d preserved",
                project_id, file_impact.get("total_affected", 0), file_impact.get("total_preserved", 0),
            )
            # Store file-level analysis in project.json for UI display
            self.workspace.update_project_json(project_id, {
                "file_impact_analysis": file_impact
            })

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

    def _await_gate(self, project_id: str, gate: str) -> PipelineResult:
        """Return a requires_user_action PipelineResult for the given gate.

        Called when run() is called while a human collaboration gate is active.
        The user must call POST /workflow/{id}/gates/{gate}/approve (or revise/adjust)
        to resume the pipeline. This method never blocks — it just returns the pause state.
        """
        _gate_to_action = {
            "architecture": ("review_architecture", "Architecture ready for review. Approve or request revisions via the gates API."),
            "design":       ("review_design",       "Design ready for review. Approve or request revisions via the gates API."),
            "sprint_plan":  ("review_sprint_plan",  "Sprint plan ready for review. Approve or adjust via the gates API."),
        }
        state = self.workspace.get_state(project_id)
        action_needed, message = _gate_to_action.get(gate, ("review", "Awaiting review."))
        data = self.workspace.load_project_json(project_id) or {}
        logger.info("_await_gate: project=%s gate=%s state=%s", project_id, gate, state)
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=False,
            requires_user_action=True,
            action_needed=action_needed,
            message=message,
            completed_stages=list(data.get("stages_completed", [])),
        )

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

    def _run_domain_research(self, project_id: str, request: str) -> dict | None:
        """Run DomainResearcherAgent before Q&A to get domain-specific context.

        DomainResearcherAgent is injected into WorkflowManager rather than going
        through AgentFactory.  It runs *before* the sprint pipeline starts, so it
        is not a pipeline stage and does not go through engine.run_stage().
        Inject it at WorkflowManager construction time; if None the step is skipped
        (non-fatal — Q&A proceeds without domain enrichment).

        Returns the DomainBrief as a dict, or None if the agent is not wired in
        or if it fails.
        """
        if self.domain_researcher is None:
            return None
        try:
            brief = self.domain_researcher.research(request)
            brief_dict = brief.model_dump(mode="json") if hasattr(brief, "model_dump") else {}
            # Persist as a stage artifact so downstream agents can reference it
            from ..shared.enums.stage import Stage
            self.artifact_manager.save_artifact(
                project_id=project_id,
                stage=Stage.DomainResearch,
                content=str(brief_dict),
                structured_content=brief_dict,
            )
            logger.info(
                "Domain research complete for %s: domain=%s complexity=%s",
                project_id, brief_dict.get("domain"), brief_dict.get("complexity"),
            )
            return brief_dict
        except Exception as exc:
            logger.warning("Domain research failed (non-fatal): %s", exc)
            return None

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
                return self._run_sprint_with_retry(project_id, sprint)
        return SprintResult(all_sprints_complete=True)

    def _run_sprint_with_retry(self, project_id: str, sprint: Sprint, max_attempts: int | None = None) -> SprintResult:
        """Run a sprint, retrying once on failure before giving up.

        Sprint-level retry is distinct from stage-level retry (WorkflowEngine.run()
        retries each LLM call up to RetryPolicy.max_retries times). This adds a
        coarser outer retry: if the whole sprint (file plan + backend + frontend)
        fails, we try the entire sprint once more before reporting failure.
        This handles transient execution errors (e.g. file write race, LLM timeout)
        that are unlikely to repeat on a second full attempt.
        """
        if max_attempts is None:
            max_attempts = getattr(self._sprint_retry, 'max_dev_review_iterations', 2) if self._sprint_retry else 2
            
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

        Injects:
          - SprintMonitor brief (file-level context from all previous sprints) — FIX 5
          - Architecture spec
          - ScrumMaster plan
        """
        # FIX 5: Sprint brief from SprintMonitor includes previous-sprint file summaries
        sprint_brief = ""
        if self.sprint_monitor is not None:
            try:
                sprint_brief = self.sprint_monitor.generate_sprint_brief(
                    project_id=project_id,
                    sprint_number=sprint.sprint_number,
                    sprint_goal=sprint.goal,
                )
            except Exception as exc:
                logger.debug("SprintMonitor.generate_sprint_brief failed (non-fatal): %s", exc)

        arch_text = getattr(arch, "content", str(arch)) if arch else ""
        scrum_artifact = self.artifact_manager.get_artifact(project_id, Stage.ScrumMaster)
        scrum_text = getattr(scrum_artifact, "content", "") if scrum_artifact else ""

        parts: list[str] = []
        if sprint_brief:
            parts.append(sprint_brief)
        else:
            parts.extend([
                f"Sprint {sprint.sprint_number}: {sprint.name}",
                f"Goal: {sprint.goal}",
                f"Features: {', '.join(sprint.features)}",
            ])

        parts.append(f"\nArchitecture Spec:\n{arch_text[:1500]}")
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
                # Normalise: WriteFilePlanAction saves files as list[PlannedFile]
                # but FilePlan.files expects dict[str, FileSpec].  Convert so that
                # tech_stack and sprint metadata are accessible to the sprint runner.
                raw_files = struct.get("files")
                if isinstance(raw_files, list):
                    files_dict: dict = {}
                    for entry in raw_files:
                        if isinstance(entry, dict):
                            path = entry.get("path", "")
                        else:
                            path = getattr(entry, "path", "")
                        if path:
                            files_dict[path] = {
                                "file_path": path,
                                "purpose": (entry.get("purpose", "") if isinstance(entry, dict)
                                            else getattr(entry, "purpose", "")),
                            }
                    struct = {**struct, "files": files_dict,
                              "project_id": project_id, "sprint_number": sprint_number}
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
        # Create the sprint-scoped artifact directory before any agent writes to it.
        self.workspace.create_sprint_folder(project_id, sprint.sprint_number)

        arch = self.artifact_manager.get_artifact(project_id, Stage.Architect)
        plan_context = self._build_sprint_context(project_id, sprint, arch)
        self.broadcaster.stage_started(project_id, "FileStructurePlanner", 1)
        plan_result = self._run_stage(project_id, "file_planner", plan_context)

        if not plan_result.success:
            self.broadcaster.stage_failed(project_id, "FileStructurePlanner", plan_result.message)
            return SprintResult(success=False, message=plan_result.message)
        
        self.broadcaster.stage_complete(project_id, "FileStructurePlanner", 1, 0)

        # Mirror file_plan into sprint-scoped ArtifactStore.
        self._persist_to_artifact_store(
            project_id,
            Stage.FileStructurePlanner,
            f"sprint_{sprint.sprint_number}",
            "file_plan",
        )

        file_plan = self._load_file_plan(project_id, sprint.sprint_number)

        if sprint.sprint_number == 1:
            tech_stack = getattr(file_plan, "tech_stack", {}) or {}
            self.project_writer.initialize_project(project_id, tech_stack)

        self.broadcaster.stage_started(project_id, "BackendDeveloper", 1)
        backend_result = self.run_stage(project_id, "backend", plan_context)
        if backend_result.success:
            self.broadcaster.stage_complete(project_id, "BackendDeveloper", 1, 0)
        else:
            self.broadcaster.stage_failed(project_id, "BackendDeveloper", backend_result.message)

        self.broadcaster.stage_started(project_id, "FrontendDeveloper", 1)
        frontend_result = self.run_stage(project_id, "frontend", plan_context)
        if frontend_result.success:
            self.broadcaster.stage_complete(project_id, "FrontendDeveloper", 1, 0)
        else:
            self.broadcaster.stage_failed(project_id, "FrontendDeveloper", frontend_result.message)

        all_success = bool(backend_result.success and frontend_result.success)
        if all_success:
            # FIX A-03: Run sprint_deploy and sprint_review manually and emit status events
            try:
                # Deploy
                self.broadcaster.stage_started(project_id, "SprintDeploy")
                deploy_agent = self._agent_factory.create("sprint_deploy")
                deploy_agent._workspace_manager = self.workspace_manager
                file_plan_dict = file_plan.model_dump(mode="json") if hasattr(file_plan, "model_dump") else (file_plan if isinstance(file_plan, dict) else {})
                deploy_status = deploy_agent.deploy_sprint(
                    project_id, 
                    sprint.sprint_number, 
                    file_plan_dict
                )
                self.broadcaster.stage_complete(project_id, "SprintDeploy", 1, 0)

                # Review
                self.broadcaster.stage_started(project_id, "SprintReview")
                review_agent = self._agent_factory.create("sprint_review")
                review_agent._workspace_manager = self.workspace_manager
                qa_findings = self.workspace.load_project_json(project_id).get(f"sprint_{sprint.sprint_number}_issues", [])
                
                scrum_art = self.artifact_manager.get_artifact(project_id, Stage.ScrumMaster)
                user_stories = getattr(scrum_art, "structured_content", {}) if scrum_art else {}
                if not isinstance(user_stories, dict):
                    user_stories = {}
                
                review_agent.review_sprint(project_id, sprint.sprint_number, user_stories, deploy_status, qa_findings)
                self.broadcaster.stage_complete(project_id, "SprintReview", 1, 0)
            except Exception as e:
                logger.warning("Failed to run sprint deploy/review for %s: %s", project_id, e, exc_info=True)

            self.workspace.mark_sprint_complete(project_id, sprint.sprint_number)
            # FIX 3: Validate sprint output against architecture contracts (non-blocking)
            if self.sprint_monitor is not None:
                try:
                    issues = self.sprint_monitor.validate_sprint_output(
                        project_id, sprint.sprint_number
                    )
                    if issues:
                        logger.warning(
                            "Sprint %d validation issues for %s: %s",
                            sprint.sprint_number, project_id, issues,
                        )
                        self.workspace.update_project_json(project_id, {
                            f"sprint_{sprint.sprint_number}_issues": issues
                        })
                except Exception as exc:
                    logger.debug("SprintMonitor.validate_sprint_output failed (non-fatal): %s", exc)

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

    def _persist_to_artifact_store(
        self,
        project_id: str,
        stage: Stage,
        scope: str,
        artifact_name: str,
    ) -> None:
        """Mirror a just-completed stage's output into ArtifactStore (non-fatal).

        Reads the artifact the engine just wrote via ArtifactManager
        (``artifacts/{stage}.json``) and writes a scoped copy to the new
        sprint/project ArtifactStore layout without removing the original.

        Parameters
        ----------
        project_id:
            The project being processed.
        stage:
            The :class:`~app.shared.enums.stage.Stage` enum value whose output
            to read back from ArtifactManager.
        scope:
            ArtifactStore scope, e.g. ``"project"`` or ``"sprint_1"``.
        artifact_name:
            Logical artifact name inside the scope, e.g. ``"user_stories"``.
        """
        try:
            artifact = self.artifact_manager.get_artifact(project_id, stage)
            if artifact is None:
                logger.debug(
                    "[ArtifactStore] skip persist — ArtifactManager has no entry for %s/%s",
                    project_id, stage.value,
                )
                return
            store = self.workspace_manager.get_artifact_store(project_id)
            store.write(
                scope=scope,
                name=artifact_name,
                data={
                    "content": artifact.content or "",
                    "stage": stage.value,
                    "written_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.debug(
                "[ArtifactStore] persisted %s → %s/%s",
                stage.value, scope, artifact_name,
            )
        except Exception as exc:  # never block the pipeline
            logger.warning(
                "[ArtifactStore] non-fatal persist failure for %s/%s → %s/%s: %s",
                project_id, stage.value, scope, artifact_name, exc,
            )

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

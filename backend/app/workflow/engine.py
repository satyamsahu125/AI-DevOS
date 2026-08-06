from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..execution.manager import ExecutionManager
from ..llm.cost_tracker import get_shared_cost_tracker
from ..memory.learning_loop import LearningLoop, Trajectory
from ..memory.lesson_store import Lesson, LessonStore, new_lesson_id
from ..memory.manager import MemoryManager
from ..memory.project_event_log import ProjectEventLog
from ..review.reviewer import Reviewer
from ..session.checkpoint import CheckpointManager, SessionCheckpoint
from ..session.manager import SessionManager
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.session_state import SessionState
from ..shared.enums.stage import Stage
from ..shared.enums.workflow_state import WorkflowState
from ..shared.models.stage_artifact import StageArtifact
from ..shared.models.workflow import Workflow
from ..shared.schemas.message import AgentMessage
from ..workspace.manager import WorkspaceManager
from ..memory.orchestrator import MemoryOrchestrator
from .execution_state import ExecutionStateRegistry
from .retry_engine import IntelligentRetryEngine
from .retry_policy import RetryPolicy
from .state_machine import WorkflowStateMachine

logger = logging.getLogger(__name__)

_WORKFLOW_MESSAGE_KEY = "workflow:latest_message"
_DESIGN_MEMORY_KEY = "design:latest"
_DESIGN_DEPENDENT_STAGES = (Stage.FrontendDeveloper.value, Stage.QA.value, Stage.FileStructurePlanner.value)


class WorkflowEngine:
    """Runs one workflow stage through its full execute -> review -> retry cycle.

    Owns the StageSession for the stage being run and consults RetryPolicy
    after every rejected review, retrying execution until either the
    Reviewer approves the artifact or the retry limit is exhausted. Uses the
    real three-tier Reviewer (review/reviewer.py, AUTO_FIX/ASK_HUMAN/FLAG),
    not just an "is content non-empty" check -- so a stage only approves
    once it clears actual quality gates (schema presence, content length,
    Designer-specific structural checks, etc.). After an approval it also
    records an AgentMessage (see shared/schemas/message.py) to memory, so
    the next stage's run() can read its predecessor's structured output.

    The predecessor message and the design memory slot are both namespaced
    by project_id (see memory/manager.py's MemoryManager.store/load), so two
    projects running concurrently never see each other's predecessor output
    or approved design spec -- each project gets its own single-slot inbox,
    not a shared global one.

    Also persists the approved Designer artifact to a separate, durable
    design memory slot (unlike the single-slot predecessor message, this
    survives however many stages run in between) and injects it into
    FrontendDeveloper and QA's content -- so no frontend code is ever
    written, and no QA plan ever authored, without an approved design spec.

    Also wires in LearningLoop (see memory/learning_loop.py): before running,
    it injects semantically-relevant past successes into the content the
    agent sees; after every attempt (approved or rejected) it records a
    Trajectory, so future stages' pattern search only ever surfaces things
    that actually worked.

    Also wires in CheckpointManager (see session/checkpoint.py, inspired by
    gstack's /context-save + /context-restore): a checkpoint is saved before
    each execution attempt and deleted once the session closes successfully,
    so a checkpoint left behind after a crash marks that session as
    incomplete. On construction, any such incomplete sessions are logged.

    Also wires in LessonStore (see memory/lesson_store.py, inspired by
    gstack's /learn skill): after every approval, a human-readable Lesson is
    extracted from the reviewer's feedback and this stage's retry history.
    """

    def __init__(
        self,
        execution_manager: ExecutionManager | None = None,
        memory_manager: MemoryManager | None = None,
        learning_loop: LearningLoop | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        lesson_store: LessonStore | None = None,
        artifact_manager: ArtifactManager | None = None,
        workspace_manager: WorkspaceManager | None = None,
        reviewer: Reviewer | None = None,
        retry_policy: RetryPolicy | None = None,
        event_log: ProjectEventLog | None = None,
        execution_state: ExecutionStateRegistry | None = None,
        broadcaster: Any | None = None,
        context_orchestrator: Any | None = None,
        config_manager: ConfigurationManager | None = None,
        memory_orchestrator: MemoryOrchestrator | None = None,
        retry_engine: IntelligentRetryEngine | None = None,
    ) -> None:
        """Wire up the collaborators needed to run a single workflow stage."""
        self.state_machine = WorkflowStateMachine()
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.execution_manager = execution_manager or ExecutionManager(self.artifact_manager)
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.session_manager = SessionManager()
        self.memory_manager = memory_manager or MemoryManager()
        self.learning_loop = learning_loop or LearningLoop()
        self.retry_policy = retry_policy or RetryPolicy()
        self.reviewer = reviewer or Reviewer(learning_loop=self.learning_loop)
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.lesson_store = lesson_store or LessonStore()
        self.event_log = event_log or ProjectEventLog()
        self.execution_state = execution_state or ExecutionStateRegistry()
        self.context_orchestrator = context_orchestrator  # None = intelligence layer disabled
        self.memory_orchestrator = memory_orchestrator    # None = legacy _with_*() chain used
        self.retry_engine = retry_engine                  # None = legacy RetryPolicy used
        self.model_router = None     # BUG-5: set by container, wires per-stage LLM profiles
        self.template_engine = None  # BUG-5: set by container, wires structural templates
        if broadcaster is not None:
            self.broadcaster = broadcaster
        else:
            from ..events.broadcaster import broadcaster as default_broadcaster
            self.broadcaster = default_broadcaster
        config_mgr = config_manager or ConfigurationManager()
        settings = config_mgr.load() if hasattr(config_mgr, "load") else getattr(config_mgr, "settings", lambda: getattr(config_mgr, "_settings", None))()
        if not settings and hasattr(config_mgr, "load"):
             settings = config_mgr.load()
        self._llm_model = settings.llm.model
        self._llm_provider = settings.llm.provider  # explicit provider from LLM_PROVIDER env var
        self._report_incomplete_sessions()

    def _report_incomplete_sessions(self) -> None:
        """Log any checkpoints left behind by sessions that never closed successfully (crash recovery)."""
        incomplete = self.checkpoint_manager.list_incomplete()
        if incomplete:
            logger.warning(
                "found %s incomplete session(s) from a previous run: %s",
                len(incomplete), [(c.session_id, c.stage, c.attempt_number) for c in incomplete],
            )

    def run(self, project_id: str, stage_name: str, content: str) -> WorkflowResult:
        """Execute stage_name with content for project_id, retrying on rejection per RetryPolicy.

        Creates one StageSession for the stage, loops execute -> review while
        the RetryPolicy permits another attempt, and closes the session on
        both the approval and retry-exhaustion exit paths. Every retry after
        the first has the previous attempt's reviewer feedback appended to
        the prompt (see _build_retry_content), so the agent knows what to
        fix instead of blindly resending the same input. On approval,
        records an AgentMessage for the next stage to read, marks this
        attempt's artifact approved, and updates project_id's workspace
        project.json (current_stage/stages_completed). Every attempt
        (approved or rejected) is also recorded as a LearningLoop Trajectory
        and saved as its own numbered artifact attempt (never overwritten).
        """
        logger.info("workflow run started: project_id=%s stage=%s", project_id, stage_name)
        self.event_log.record(project_id, stage_name, f"{stage_name} started")
        self.state_machine.start()
        session = self.session_manager.create_session(stage_name)

        import json as _json_run
        stage = Stage(stage_name)
        workflow = Workflow(id="", project_id=project_id, current_stage=stage, state=WorkflowState.Created)

        if self.memory_orchestrator is not None:
            # New path: MemoryOrchestrator assembles all four memory layers into StageContext.
            # Patterns and lessons are included via Layer 3 (Semantic) in the orchestrator.
            try:
                stage_ctx = self.memory_orchestrator.get_context(project_id, stage)
                base_content = _json_run.dumps(stage_ctx.to_prompt_dict(), indent=2)
                logger.debug("run: using MemoryOrchestrator for context assembly: stage=%s", stage_name)
            except Exception as _orch_exc:
                logger.warning("MemoryOrchestrator.get_context failed for %s/%s, falling back to legacy chain: %s", project_id, stage_name, _orch_exc)
                base_content = self._legacy_enrich(project_id, stage_name, content)
        else:
            # Legacy path: six ad-hoc _with_*() enrichment calls. Kept for backward
            # compat until MemoryOrchestrator is wired in Container and verified.
            base_content = self._legacy_enrich(project_id, stage_name, content)

        # BUG-5 fix: inject structural template from similar past approvals.
        base_content = self._inject_template(stage_name, project_id, base_content)
        # BUG-4 fix: inject human gate feedback for revised stages.
        base_content = self._with_gate_feedback(project_id, stage_name, base_content)
        # R2: inject real sandbox lint/test/build results into bug_analyst context.
        base_content = self._inject_sandbox_results(project_id, stage_name, base_content)

        if hasattr(self.execution_manager, "llm_manager") and self.execution_manager.llm_manager:
            self.execution_manager.llm_manager.set_context(project_id, stage_name)
        # BUG-5 fix: apply ModelRouter per-stage profile to LLM manager if wired.
        self._apply_model_router_profile(project_id, stage_name)

        attempt = 0
        review_result = None
        reviewer_feedback = ""
        failed_approaches: list[str] = []
        last_artifact_summary = ""
        last_error = ""
        stage_start_time = datetime.now(timezone.utc)
        while self.retry_policy.should_retry(attempt):
            if self.execution_state.is_stop_requested(project_id):
                logger.info("workflow stage stopped by user: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(project_id, stage_name, f"{stage_name} stopped by user before attempt {attempt + 1}", level="warning")
                self.session_manager.close_session(session)
                return WorkflowResult(workflow=workflow, success=False, message="Stopped by user", stopped=True)
            logger.info("workflow stage attempt: stage=%s attempt=%s", stage_name, attempt)
            self.broadcaster.stage_started(project_id, stage_name, attempt + 1)
            self.event_log.record(project_id, stage_name, f"Attempt {attempt + 1}: generating with the AI model...")
            self.broadcaster.log_line(project_id, stage_name, f"Attempt {attempt + 1}: generating with the AI model...")
            effective_content = base_content if attempt == 0 else self._build_retry_content(base_content, reviewer_feedback, attempt)
            self._save_checkpoint(session.session_id, stage_name, project_id, attempt, failed_approaches, last_artifact_summary)
            try:
                execution_result = self.execution_manager.execute_stage(project_id, stage_name, effective_content, attempt=attempt + 1)
                artifact = execution_result.artifact
                previous_content = last_artifact_summary or None
                last_artifact_summary = (artifact.content or "")[:300]
                review_result = self.reviewer.review(artifact, previous_content=previous_content)
                self._record_trajectory(stage_name, content, artifact, attempt, review_result, project_id)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("workflow stage attempt raised: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(
                    project_id, stage_name,
                    f"Attempt {attempt + 1} failed: {last_error}",
                    level="error",
                )
                self.broadcaster.stage_retry(project_id, stage_name, attempt + 2, last_error)
                failed_approaches.append(last_error)
                session.state = SessionState.Rejected
                self.session_manager.increment_retry(session)
                attempt += 1
                continue

            if review_result.approved:
                logger.info("workflow stage approved: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(project_id, stage_name, f"{stage_name} approved on attempt {attempt + 1}")
                duration_sec = (datetime.now(timezone.utc) - stage_start_time).total_seconds()
                workflow.state = WorkflowState.Approved
                self.state_machine.approve()
                self.state_machine.complete()
                self.session_manager.close_session(session)
                self._record_message(project_id, stage, artifact)
                self._record_design(project_id, stage, artifact)
                self._record_sprint_plan(project_id, stage, artifact)
                self._record_lesson(stage_name, project_id, artifact, attempt, review_result, failed_approaches)
                # BUG-5 fix: extract structural template from approved artifact for future runs.
                self._extract_template(stage_name, project_id, artifact)
                # R4: commit stage artifact to git history.
                self._commit_stage_to_git(project_id, stage_name, artifact)
                if self.memory_orchestrator is not None:
                    _struct = getattr(artifact, "structured_content", None) or {}
                    self.memory_orchestrator.record_approval(project_id, stage, _struct)
                self.checkpoint_manager.delete(session.session_id)
                self.artifact_manager.mark_approved(project_id, stage, attempt + 1)
                self._update_project_progress(project_id, stage)
                # Recompute progress after the stage is recorded and push to frontend.
                self.broadcaster.stage_complete(
                    project_id, stage_name, attempt + 1, duration_sec,
                    progress_percent=self._compute_progress_percent(project_id),
                )
                # R7: Check context window usage — broadcast warning if > 75% of provider limit.
                self._check_context_window(project_id)
                # BUG-3 fix: include approved artifact so PipelineSupervisor.BugAnalyst
                # rollback logic can read artifact.structured_content.
                return WorkflowResult(workflow=workflow, success=True, message="workflow completed", artifact=artifact)

            reviewer_feedback = self._detailed_feedback(review_result)
            logger.warning(
                "workflow stage rejected: stage=%s attempt=%s feedback=%s",
                stage_name, attempt, reviewer_feedback,
            )
            self.event_log.record(project_id, stage_name, f"Attempt {attempt + 1} rejected: {review_result.overall_feedback}", level="warning")
            failed_approaches.append(reviewer_feedback)
            if self.memory_orchestrator is not None:
                self.memory_orchestrator.record_rejection(project_id, stage, reviewer_feedback)

            # IntelligentRetryEngine: get a structured plan for the next attempt.
            if self.retry_engine is not None:
                retry_plan = self.retry_engine.plan(
                    attempt=attempt + 1,  # next attempt index
                    review_result=review_result,
                    stage=stage_name,
                    project_id=project_id,
                )
                logger.debug("retry_engine decision: %s", retry_plan)
                if retry_plan.prompt_instruction:
                    reviewer_feedback = f"{reviewer_feedback}\n{retry_plan.prompt_instruction}"
                if retry_plan.should_stop:
                    self.broadcaster.stage_retry(project_id, stage_name, attempt + 2, reviewer_feedback)
                    session.state = SessionState.Rejected
                    self.session_manager.increment_retry(session)
                    attempt += 1
                    break  # explicit early exit — retry_engine said stop
            self.broadcaster.stage_retry(project_id, stage_name, attempt + 2, reviewer_feedback)
            session.state = SessionState.Rejected
            self.session_manager.increment_retry(session)
            attempt += 1

        logger.error("workflow stage exhausted retries: stage=%s attempts=%s", stage_name, attempt)
        self.event_log.record(project_id, stage_name, f"{stage_name} failed after {attempt} attempt(s)", level="error")
        self.broadcaster.stage_failed(project_id, stage_name, f"Exhausted retries ({attempt} attempts)")
        workflow.state = WorkflowState.Failed
        self.state_machine.fail()
        self.session_manager.close_session(session)
        # Close out the checkpoint on the failure path too. Previously only the
        # approval path deleted it, so every failed stage left one behind and
        # list_incomplete() filled up with stale sessions from old runs.
        self.checkpoint_manager.delete(session.session_id)
        if review_result is not None:
            message = review_result.overall_feedback
        elif last_error:
            # Every attempt raised before producing an artifact -- report the
            # actual cause rather than the misleading "no execution attempted".
            message = f"{stage_name} could not run: {last_error}"
        else:
            message = "no execution attempted"
        self._update_project_failure(project_id, stage)
        return WorkflowResult(workflow=workflow, success=False, message=message)

    def _legacy_enrich(self, project_id: str, stage_name: str, content: str) -> str:
        """Six ad-hoc enrichment calls — kept as fallback until MemoryOrchestrator is fully wired."""
        base = self._with_predecessor_message(project_id, content)
        base = self._with_clarification_context(project_id, stage_name, base)
        base = self._with_relevant_patterns(base, stage_name, content, project_id)
        base = self._with_design_context(project_id, base, stage_name)
        base = self._with_lessons(base, stage_name, project_id)
        base = self._with_intelligence_context(project_id, stage_name, base)
        return base

    def _detailed_feedback(self, review_result) -> str:
        """Build actionable feedback from every ReviewFinding (description + suggestion), not just the
        one-line overall_feedback summary -- the summary alone ("Rejected: 1 ask_human.") gives the agent
        no idea what to actually fix on retry, so retries kept reproducing the same rejected shape."""
        if not review_result.findings:
            return review_result.overall_feedback
        lines = [review_result.overall_feedback]
        for finding in review_result.findings:
            line = f"- [{finding.tier.value}] {finding.description}"
            if finding.suggestion:
                line += f" -- Suggestion: {finding.suggestion}"
            lines.append(line)
        return "\n".join(lines)

    def _build_retry_content(self, original_content: str, reviewer_feedback: str, attempt: int) -> str:
        """Rebuild stage input with the previous attempt's reviewer feedback injected, so the agent
        knows what to fix on retry instead of blindly resending the same prompt."""
        return (
            f"{original_content}\n\n"
            f"--- REVIEWER FEEDBACK (Attempt {attempt}) ---\n"
            f"Your previous output was rejected for the following reasons:\n"
            f"{reviewer_feedback}\n"
            f"Please address all feedback points in your next response.\n"
            f"--- END FEEDBACK ---"
        )

    def _update_project_progress(self, project_id: str, stage: Stage) -> None:
        """Record stage as completed in project_id's workspace project.json, clearing any prior failed_stage."""
        if not project_id:
            return
        existing = self.workspace_manager.load_project_json(project_id) or {}
        completed = list(existing.get("stages_completed", []))
        if stage.value not in completed:
            completed.append(stage.value)
        self.workspace_manager.update_project_json(project_id, {
            "current_stage": stage.value,
            "stages_completed": completed,
            "failed_stage": None,
        })

    def _compute_progress_percent(self, project_id: str) -> int:
        """Return 0-100 progress using the same inflation logic as the status API.

        Reads the current project.json so the value reflects the just-completed stage.
        Non-STAGE_ORDER stages (DomainResearch, Clarifying, sprint sub-stages) are
        re-added based on the current pipeline state so the count matches the 20-stage
        STAGES array used by the frontend.
        """
        data = self.workspace_manager.load_project_json(project_id) or {}
        state_str = data.get("state", "")
        completed = list(data.get("stages_completed", []))

        _PRE_PIPELINE = ["DomainResearch", "Clarifying"]
        _SPRINT_SUB = [
            "ScrumMaster", "FileStructurePlanner", "BackendDeveloper",
            "FrontendDeveloper", "SprintDeploy", "SprintReview",
        ]
        _POST_SPRINT = frozenset({
            "all_sprints_complete", "qa_complete", "deployable", "done",
            "resuming_from_change",
        })

        if state_str not in ("", "empty", "not_started"):
            for s in _PRE_PIPELINE:
                if s not in completed:
                    completed.append(s)

        if state_str in _POST_SPRINT:
            for s in _SPRINT_SUB:
                if s not in completed:
                    completed.append(s)

        if state_str in ("deployable", "done"):
            return 100

        return round(100 * len(completed) / 20) if completed else 0

    def _update_project_failure(self, project_id: str, stage: Stage) -> None:
        """Record stage as the one that exhausted its retries in project_id's workspace project.json."""
        if not project_id:
            return
        self.workspace_manager.update_project_json(project_id, {"failed_stage": stage.value})

    def _save_checkpoint(
        self, session_id: str, stage_name: str, project_id: str, attempt: int,
        failed_approaches: list[str], last_artifact_summary: str,
    ) -> None:
        """Save a resumable checkpoint before this attempt's LLM call (see session/checkpoint.py)."""
        checkpoint = SessionCheckpoint(
            session_id=session_id,
            stage=stage_name,
            project_id=project_id,
            attempt_number=attempt,
            failed_approaches=list(failed_approaches),
            last_artifact_summary=last_artifact_summary,
        )
        self.checkpoint_manager.save(session_id, checkpoint)

    def _with_relevant_patterns(self, content: str, stage_name: str, task: str, project_id: str) -> str:
        """Prepend semantically-relevant past successful trajectories for this exact project/stage, if any exist.

        Scoped strictly to project_id so one project's past output never
        gets suggested as a "relevant pattern" for an unrelated project
        working on the same stage (this was a real, observed bug: a
        calculator-app project's ProductOwner stage got an invoice-app
        pattern injected from an earlier, unrelated project's run).
        """
        patterns = self.learning_loop.get_relevant_patterns(task, stage_name, project_id=project_id)
        if not patterns:
            return content
        patterns_text = "\n".join(f"- {pattern}" for pattern in patterns)
        return f"{content}\n\n### Relevant Past Patterns\n{patterns_text}"

    def _record_trajectory(
        self, stage_name: str, task: str, artifact: StageArtifact, attempt: int, review_result, project_id: str,
    ) -> None:
        """Record this attempt (approved or rejected) as a LearningLoop Trajectory, tagged with project_id
        so get_relevant_patterns() can scope its search to this same project."""
        tracker = get_shared_cost_tracker()
        trajectory = Trajectory(
            stage=stage_name,
            task_description=task,
            artifact_summary=(artifact.content or "")[:300],
            retry_count=attempt,
            approved=review_result.approved,
            reviewer_feedback=review_result.overall_feedback,
            agent_model=self._llm_model,
            tokens_used=tracker.last_call_tokens,
            latency_ms=tracker.last_call_latency,
            project_id=project_id,
        )
        self.learning_loop.record_trajectory(trajectory)

    def _record_lesson(
        self, stage_name: str, project_id: str, artifact: StageArtifact, attempt: int,
        review_result, failed_approaches: list[str],
    ) -> None:
        """Extract a human-readable Lesson from this approval and store it via LessonStore."""
        lesson = Lesson(
            lesson_id=new_lesson_id(),
            stage=stage_name,
            project_id=project_id,
            what_worked=(artifact.content or "")[:300],
            what_failed="; ".join(failed_approaches),
            reviewer_said=review_result.overall_feedback,
            retry_count_when_learned=attempt,
            created_at=datetime.now(timezone.utc),
        )
        self.lesson_store.add_lesson(lesson)

    def _with_design_context(self, project_id: str, content: str, stage_name: str) -> str:
        """Prepend the approved DesignArtifact for stages that must never work without an approved design spec.

        Unlike the predecessor-message slot, this is a durable key that
        survives however many stages run between Designer and the stages
        that depend on it (FrontendDeveloper, QA) -- not just the
        immediately-preceding stage. Namespaced by project_id so concurrent
        projects never see each other's design spec.
        """
        if stage_name not in _DESIGN_DEPENDENT_STAGES:
            return content
        design_entry = self.memory_manager.load(project_id, _DESIGN_MEMORY_KEY)
        if not design_entry:
            return content
        return f"{content}\n\n### Approved Design Spec\n{design_entry}"

    def _with_lessons(self, content: str, stage_name: str, project_id: str) -> str:
        """Prepend human-readable lessons from LessonStore for this exact stage/project.

        LessonStore (see memory/lesson_store.py) holds curated, human-readable lessons
        learned from prior approvals for this stage — distinct from LearningLoop's
        semantic vector search. Injecting them here means every retry attempt for a
        stage benefits from what the reviewer explicitly approved before, not just
        semantic similarity. Only the 3 most recent lessons are injected to keep
        the prompt compact.
        """
        lessons = self.lesson_store.get_lessons(stage=stage_name, project_id=project_id, limit=3)
        if not lessons:
            return content
        lines = [f"### Lessons Learned for {stage_name} (this project)"]
        for lesson in lessons:
            lines.append(f"- What worked: {lesson.what_worked[:200]}")
            if lesson.what_failed:
                lines.append(f"  What failed: {lesson.what_failed[:150]}")
            if lesson.reviewer_said:
                lines.append(f"  Reviewer said: {lesson.reviewer_said[:150]}")
        return f"{content}\n\n" + "\n".join(lines)

    def _with_intelligence_context(self, project_id: str, stage_name: str, content: str) -> str:
        """Prepend intelligence context (file index, dependency graph, project overview) via ContextOrchestrator.

        Only runs when ``self.context_orchestrator`` is set (registered in Container).
        Gracefully skips on any error so it never blocks the main pipeline.
        """
        if self.context_orchestrator is None:
            return content
        try:
            package = self.context_orchestrator.build(
                project_id=project_id,
                stage=stage_name,
                task_description=content[:200],  # keyword hint only — keep it fast
            )
            prefix = self.context_orchestrator.format_as_prompt_section(package)
            if prefix:
                return f"{prefix}\n\n━━━ YOUR TASK ━━━\n{content}"
        except Exception as exc:
            logger.debug("ContextOrchestrator skipped for %s/%s: %s", project_id, stage_name, exc)
        return content

    def _record_design(self, project_id: str, stage: Stage, artifact: StageArtifact) -> None:
        """Persist an approved Designer artifact to project_id's durable design memory slot."""
        if stage != Stage.Designer:
            return
        self.memory_manager.store(project_id, _DESIGN_MEMORY_KEY, artifact.content)
        logger.debug("design artifact recorded: project_id=%s key=%s", project_id, _DESIGN_MEMORY_KEY)

    def _record_sprint_plan(self, project_id: str, stage: Stage, artifact: StageArtifact) -> None:
        """Persist an approved SprintPlan artifact to workspace project.json and artifacts/sprint_plan.json."""
        if stage != Stage.SprintPlanning and stage.value not in ("SprintPlanning", "SprintPlanner", "Planner"):
            return
        if not project_id or not artifact:
            return
        structured = getattr(artifact, "structured_content", None) or {}
        raw_content = artifact.content or "{}"
        from ..actions.base_action import BaseAction
        sprint_plan_data = structured if structured else BaseAction.extract_json(raw_content)

        if sprint_plan_data:
            try:
                if "project_id" not in sprint_plan_data or not sprint_plan_data["project_id"]:
                    sprint_plan_data["project_id"] = project_id
                if "created_at" not in sprint_plan_data or not sprint_plan_data["created_at"]:
                    sprint_plan_data["created_at"] = datetime.now(timezone.utc).isoformat()
                from ..shared.models.sprint import SprintPlan
                plan_model = SprintPlan.model_validate(sprint_plan_data)
                self.workspace_manager.update_sprint_plan(project_id, plan_model)
                sprint_plan_file = self.workspace_manager.get_workspace_path(project_id) / "artifacts" / "sprint_plan.json"
                sprint_plan_file.parent.mkdir(parents=True, exist_ok=True)
                import json
                sprint_plan_file.write_text(json.dumps(plan_model.model_dump(mode="json"), indent=2), encoding="utf-8")
                logger.info("sprint plan recorded: project_id=%s total_sprints=%s", project_id, plan_model.total_sprints)
            except Exception as exc:
                logger.warning("failed to parse or save sprint plan: %s", exc)

    def _with_clarification_context(self, project_id: str, stage_name: str, content: str) -> str:
        """For ProductOwner: rebuild content as the full JSON dict that ProductOwnerPromptBuilder
        expects (Path A), injecting the Clarification and DomainResearch artifacts that the
        predecessor chain (StrategicReview) does not carry.

        The predecessor message only contains StrategicReview's output, so without this enrichment
        ProductOwnerPromptBuilder falls into Path B and sets clarification={}, causing the model
        to produce an empty requirements list which the Reviewer then rejects as ASK_HUMAN.

        This follows the exact same pattern as _with_design_context().
        """
        if stage_name not in (Stage.ProductOwner.value, "ProductOwner", "product_owner"):
            return content

        import json as _json
        import re as _re

        # Load the Clarification artifact (saved by WorkflowManager after Q&A completes)
        clarification_artifact = self.artifact_manager.get_artifact(project_id, Stage.Clarification)
        if clarification_artifact is None:
            # Bug B fix: no Clarification artifact means QA was bypassed or failed.
            # Never send {} to ProductOwner — build a minimal context from project.json
            # so the model has at least the original request to derive requirements from.
            p_data = self.workspace_manager.load_project_json(project_id) or {}
            _orig = p_data.get("original_request") or p_data.get("description") or content
            clarification_struct = {
                "original_request": _orig,
                "project_description": _orig,
                "functional_requirements": [],
                "non_functional_requirements": [],
                "scale_profile": {
                    "user_count": "unknown",
                    "auth_needed": False,
                    "database_needed": False,
                    "infrastructure_tier": "unknown",
                },
                "inferred_scope": (
                    "No clarification was performed. "
                    "Infer full scope and requirements from the original request above."
                ),
            }
            logger.warning(
                "_with_clarification_context: no Clarification artifact for %s — "
                "using project.json fallback (original_request=%r)",
                project_id,
                _orig[:80],
            )
        else:
            clarification_struct = (
                getattr(clarification_artifact, "structured_content", None) or {}
            )

        # Load the DomainResearch artifact
        domain_artifact = self.artifact_manager.get_artifact(project_id, Stage.DomainResearch)
        domain_struct = (
            getattr(domain_artifact, "structured_content", None) or {}
            if domain_artifact else {}
        )

        # Load the StrategicReview artifact (the approved output, more reliable than memory)
        strategic_artifact = self.artifact_manager.get_artifact(project_id, Stage.StrategicReview)
        strategic_struct = (
            getattr(strategic_artifact, "structured_content", None) or {}
            if strategic_artifact else {}
        )

        # Extract original request — it's the text before the predecessor section
        split_pat = _re.compile(r"\n\n###\s+Previous Stage Output[^\n]*\n", _re.IGNORECASE)
        parts = split_pat.split(content, maxsplit=1)
        original_request = parts[0].strip() if parts else content.strip()

        full_context = _json.dumps({
            "original_request": original_request,
            "clarification":    clarification_struct,
            "strategic_brief":  strategic_struct,
            "domain_research":  domain_struct,
        }, indent=2)

        logger.debug(
            "_with_clarification_context: project=%s clarification_keys=%s strategic_keys=%s",
            project_id,
            list(clarification_struct.keys())[:5],
            list(strategic_struct.keys())[:5],
        )
        return full_context

    def _apply_model_router_profile(self, project_id: str, stage_name: str) -> None:
        """BUG-5 fix: apply the ModelRouter per-stage LLM profile to the LLM manager.

        ModelRouter.get_profile() returns a ModelProfile with temperature and
        max_tokens overrides for this stage. We push it to the LLMManager via
        set_stage_profile() so the next generate_text() call in this stage uses
        the correct parameters without needing changes to the agent call chain.
        Non-fatal: if model_router or llm_manager is unavailable, skips silently.
        """
        if self.model_router is None:
            return
        try:
            profile = self.model_router.get_profile(stage_name)
            llm = getattr(self.execution_manager, "llm_manager", None)
            if llm is not None and hasattr(llm, "set_stage_profile"):
                llm.set_stage_profile(profile)
                logger.debug(
                    "model_router profile: stage=%s temperature=%s max_tokens=%s",
                    stage_name,
                    getattr(profile, "temperature", None),
                    getattr(profile, "max_tokens", None),
                )
        except Exception as exc:
            logger.debug("_apply_model_router_profile skipped for %s/%s: %s", project_id, stage_name, exc)

    def _inject_template(self, stage_name: str, project_id: str, content: str) -> str:
        """BUG-5 fix: inject a structural template from similar past approvals.

        Finds the most similar approved artifact for this stage across past
        projects and injects its structural skeleton into content so the agent
        produces consistent output shapes. Non-fatal: returns content unchanged
        on any error.
        """
        if self.template_engine is None:
            return content
        try:
            context_dict = {"project_id": project_id, "stage": stage_name}
            similar = self.template_engine.find_similar(stage_name, context_dict, top_n=1)
            if not similar:
                return content
            injected = self.template_engine.inject_template(similar[0], context_dict)
            if injected:
                import json as _json_tmpl
                return (
                    f"{content}\n\n"
                    f"### STRUCTURAL TEMPLATE (from a similar past project)\n"
                    f"Use this structure as a starting point — fill in the correct values:\n"
                    f"{_json_tmpl.dumps(injected, indent=2)}"
                )
        except Exception as exc:
            logger.debug("_inject_template skipped for %s/%s: %s", project_id, stage_name, exc)
        return content

    def _extract_template(self, stage_name: str, project_id: str, artifact) -> None:
        """BUG-5 fix: extract a structural template from an approved artifact.

        Called after each stage approval. The extracted template is indexed by
        stage and used to inject structure into future runs of the same stage.
        Non-fatal: failures are logged at debug level.
        """
        if self.template_engine is None:
            return
        try:
            struct = getattr(artifact, "structured_content", None) or {}
            if struct:
                self.template_engine.extract_template(struct, stage_name, project_id)
                logger.debug("template_engine: template extracted for %s/%s", project_id, stage_name)
        except Exception as exc:
            logger.debug("_extract_template skipped for %s/%s: %s", project_id, stage_name, exc)

    def _commit_stage_to_git(self, project_id: str, stage_name: str, artifact) -> None:
        """R4: Commit stage artifacts to the project workspace git repository.

        Called after each stage approval so major milestones (Architecture, Design,
        DevOps, etc.) have meaningful git commits in the project history.
        Non-fatal: git errors are caught and logged; never propagates to caller.
        """
        try:
            from ..workspace.git_manager import GitManager
            workspace_path = self.workspace_manager.get_workspace_path(project_id)
            git = GitManager(workspace_path)
            # Build a meaningful commit summary from artifact content
            content_preview = ""
            if artifact is not None:
                raw = getattr(artifact, "content", "") or ""
                content_preview = raw[:100].replace("\n", " ").strip()
            summary = content_preview or stage_name
            commit_hash = git.commit_stage(stage_name, summary)
            if commit_hash:
                logger.debug(
                    "git commit after stage approval: project=%s stage=%s hash=%s",
                    project_id, stage_name, commit_hash,
                )
        except Exception as exc:
            logger.debug("_commit_stage_to_git skipped for %s/%s: %s", project_id, stage_name, exc)

    def _with_gate_feedback(self, project_id: str, stage_name: str, content: str) -> str:
        """BUG-4 fix: inject human gate feedback into context when this stage was revised.

        Gate feedback is stored by api/gates.py at key 'gate:feedback:{gate}'.
        This method reads it and prepends it so the agent knows what the human
        reviewer asked for. Only the stages that are re-run after a gate revision
        receive feedback — all other stages pass through unchanged.
        """
        _gate_stage_map = {
            Stage.Architect.value: "architecture",
            Stage.Designer.value: "design",
            Stage.SprintPlanning.value: "sprint_plan",
        }
        gate = _gate_stage_map.get(stage_name)
        if not gate:
            return content
        try:
            feedback = self.memory_manager.load(project_id, f"gate:feedback:{gate}")
            if feedback:
                logger.info(
                    "gate feedback injected: project=%s stage=%s gate=%s",
                    project_id, stage_name, gate,
                )
                return (
                    f"{content}\n\n"
                    f"--- HUMAN GATE FEEDBACK ---\n"
                    f"A human reviewer requested the following revision at the {gate} gate:\n"
                    f"{feedback}\n"
                    f"You MUST incorporate all of this feedback in your response.\n"
                    f"--- END GATE FEEDBACK ---"
                )
        except Exception as exc:
            logger.debug("_with_gate_feedback skipped for %s/%s: %s", project_id, stage_name, exc)
        return content

    def _inject_sandbox_results(self, project_id: str, stage_name: str, content: str) -> str:
        """R2: inject real sandbox lint/test/build results into the bug_analyst stage context.

        Sandbox results are stored at 'sandbox:latest' by PipelineSupervisor._run_sandbox()
        after each sprint completes. This injects them as an AUTOMATED VERIFICATION RESULTS
        block so BugAnalyst grounds its analysis in real execution output rather than
        LLM-hallucinated test descriptions.

        Only activates for bug_analyst stage. All other stages pass through unchanged.
        """
        from ..shared.enums.stage import Stage
        if stage_name != Stage.BugAnalyst.value:
            return content
        try:
            sandbox_json = self.memory_manager.load(project_id, "sandbox:latest")
            if not sandbox_json:
                return content
            import json as _json
            data = _json.loads(sandbox_json) if isinstance(sandbox_json, str) else sandbox_json
            lint_count = data.get("lint", {}).get("error_count", 0)
            build_ok = data.get("build", {}).get("success", True)
            test_passed = data.get("test", {}).get("passed", 0)
            test_total = data.get("test", {}).get("total", 0)
            lint_errors = data.get("lint", {}).get("errors", [])
            lint_lines = "\n".join(
                f"  - {e.get('file','?')}:{e.get('line',0)}: {e.get('message','')}"
                for e in lint_errors[:20]
            )
            build_errors = data.get("build", {}).get("errors", [])
            build_lines = "\n".join(f"  - {e}" for e in build_errors[:10])
            logger.info(
                "sandbox results injected into bug_analyst: project=%s lint=%d build=%s tests=%d/%d",
                project_id, lint_count, build_ok, test_passed, test_total,
            )
            return (
                f"## AUTOMATED VERIFICATION RESULTS\n"
                f"The following checks were run automatically against the generated code:\n"
                f"- Lint errors: {lint_count}\n"
                f"- Build: {'PASSED' if build_ok else 'FAILED'}\n"
                f"- Tests: {test_passed}/{test_total} passed\n\n"
                + (f"Lint issues:\n{lint_lines}\n\n" if lint_lines else "")
                + (f"Build errors:\n{build_lines}\n\n" if build_lines else "")
                + f"Your review MUST address all automated issues. "
                f"Do not approve code with lint errors or build failures.\n\n"
                f"---\n\n{content}"
            )
        except Exception as exc:
            logger.debug("_inject_sandbox_results skipped for %s/%s: %s", project_id, stage_name, exc)
        return content

    def _with_predecessor_message(self, project_id: str, content: str) -> str:
        """Prepend project_id's previous stage AgentMessage (if any) so this stage sees structured predecessor output."""
        predecessor = self._read_predecessor_message(project_id)
        if predecessor is None:
            return content
        return f"{content}\n\n### Previous Stage Output ({predecessor.role})\n{predecessor.content}"

    def _read_predecessor_message(self, project_id: str) -> AgentMessage | None:
        """Load and parse project_id's last recorded AgentMessage, if any (None if absent or unparseable)."""
        raw = self.memory_manager.load(project_id, _WORKFLOW_MESSAGE_KEY)
        if not raw:
            return None
        try:
            return AgentMessage.model_validate_json(raw)
        except Exception as exc:
            logger.debug("failed to parse predecessor AgentMessage: %s", exc)
            return None

    # R7: Provider-specific context limits (tokens). Used for context window warning.
    _CONTEXT_LIMITS: dict[str, int] = {
        "claude": 200_000,     # Claude 3+ (all variants)
        "bedrock": 200_000,    # Bedrock Claude models
        "gemini": 1_000_000,   # Gemini 1.5/2.0 (very large, warn at 750K)
        "openai": 128_000,     # GPT-4 Turbo
        "ollama": 32_000,      # Local models (conservative)
    }
    _CONTEXT_WARNING_THRESHOLD = 0.75  # warn when > 75% of limit used

    def _check_context_window(self, project_id: str) -> None:
        """R7: Check cumulative token usage for project_id and broadcast a warning if > 75% of limit.

        Uses CostTracker.get_project_cost() for the cumulative token count
        and self._llm_model to derive the provider and its context limit.
        Non-blocking — exceptions are caught and logged.
        """
        try:
            from ..llm.cost_tracker import get_shared_cost_tracker
            tracker = get_shared_cost_tracker()
            cost = tracker.get_project_cost(project_id)
            used_tokens = cost.total_tokens
            if used_tokens == 0:
                return

            # Use the explicit LLM_PROVIDER value first — model name scanning is
            # an unreliable fallback that breaks when the model name contains no
            # provider keywords (e.g. qwen.qwen3-vl-235b-a22b via Bedrock).
            provider = (self._llm_provider or "").lower().strip()
            if provider not in self._CONTEXT_LIMITS:
                # fallback: derive from model name keywords
                model_lower = (self._llm_model or "").lower()
                if "claude" in model_lower or "anthropic" in model_lower:
                    provider = "claude"
                elif "bedrock" in model_lower:
                    provider = "bedrock"
                elif "gemini" in model_lower:
                    provider = "gemini"
                elif "gpt" in model_lower or "openai" in model_lower:
                    provider = "openai"
                else:
                    provider = "ollama"

            limit = self._CONTEXT_LIMITS.get(provider, 32_000)
            pct = int(used_tokens / limit * 100)
            if pct >= int(self._CONTEXT_WARNING_THRESHOLD * 100):
                logger.warning(
                    "[engine] context window %d%% full: project=%s used=%d limit=%d provider=%s",
                    pct, project_id, used_tokens, limit, provider,
                )
                self.broadcaster.context_warning(
                    project_id=project_id,
                    used_tokens=used_tokens,
                    limit_tokens=limit,
                    pct=pct,
                )
        except Exception as exc:
            logger.debug("[engine] context window check failed (non-fatal): %s", exc)

    def _record_message(self, project_id: str, stage: Stage, artifact: StageArtifact) -> None:
        """Persist this stage's approved artifact as an AgentMessage for project_id's next stage to read."""
        message = AgentMessage(
            message_id=str(uuid4()),
            role=stage.value,
            stage=stage,
            content=artifact.content,
            structured=getattr(artifact, "structured_content", None) or {},
            cause_by=getattr(artifact, "schema_type", "") or stage.value,
            sent_at=datetime.now(timezone.utc),
        )
        self.memory_manager.store(project_id, _WORKFLOW_MESSAGE_KEY, message.model_dump_json())
        logger.debug("workflow message recorded: project_id=%s stage=%s message_id=%s", project_id, stage.value, message.message_id)

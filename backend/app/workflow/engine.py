from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..execution.manager import ExecutionManager
from ..llm.cost_tracker import get_shared_cost_tracker
from ..memory.learning_loop import LearningLoop, Trajectory
from ..memory.lesson_store import Lesson, LessonStore, new_lesson_id
from ..memory.manager import MemoryManager
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
from .dependency import WorkflowDependency
from .retry_policy import RetryPolicy
from .state_machine import WorkflowStateMachine
from .transition import WorkflowTransition

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
    ) -> None:
        """Wire up the collaborators needed to run a single workflow stage."""
        self.dependency = WorkflowDependency("ProductOwner")
        self.state_machine = WorkflowStateMachine()
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.execution_manager = execution_manager or ExecutionManager(self.artifact_manager)
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.session_manager = SessionManager()
        self.transition = WorkflowTransition()
        self.memory_manager = memory_manager or MemoryManager()
        self.learning_loop = learning_loop or LearningLoop()
        self.retry_policy = retry_policy or RetryPolicy()
        self.reviewer = reviewer or Reviewer(learning_loop=self.learning_loop)
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.lesson_store = lesson_store or LessonStore()
        self._llm_model = ConfigurationManager().load().llm.model
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
        self.state_machine.start()
        session = self.session_manager.create_session(stage_name)

        stage = Stage(stage_name)
        workflow = Workflow(id="", project_id=project_id, current_stage=stage, state=WorkflowState.Created)
        base_content = self._with_predecessor_message(project_id, content)
        base_content = self._with_relevant_patterns(base_content, stage_name, content, project_id)
        base_content = self._with_design_context(project_id, base_content, stage_name)

        attempt = 0
        review_result = None
        reviewer_feedback = ""
        failed_approaches: list[str] = []
        last_artifact_summary = ""
        while self.retry_policy.should_retry(attempt):
            logger.info("workflow stage attempt: stage=%s attempt=%s", stage_name, attempt)
            effective_content = base_content if attempt == 0 else self._build_retry_content(base_content, reviewer_feedback, attempt)
            self._save_checkpoint(session.session_id, stage_name, project_id, attempt, failed_approaches, last_artifact_summary)
            execution_result = self.execution_manager.execute_stage(project_id, stage_name, effective_content, attempt=attempt + 1)
            artifact = execution_result.artifact
            previous_content = last_artifact_summary or None
            last_artifact_summary = (artifact.content or "")[:300]
            review_result = self.reviewer.review(artifact, previous_content=previous_content)
            self._record_trajectory(stage_name, content, artifact, attempt, review_result, project_id)

            if review_result.approved:
                logger.info("workflow stage approved: stage=%s attempt=%s", stage_name, attempt)
                workflow.state = self.transition.transition(WorkflowState.Approved)
                self.state_machine.approve()
                self.state_machine.complete()
                self.session_manager.close_session(session)
                self._record_message(project_id, stage, artifact)
                self._record_design(project_id, stage, artifact)
                self._record_lesson(stage_name, project_id, artifact, attempt, review_result, failed_approaches)
                self.checkpoint_manager.delete(session.session_id)
                self.artifact_manager.mark_approved(project_id, stage, attempt + 1)
                self._update_project_progress(project_id, stage)
                return WorkflowResult(workflow=workflow, success=True, message="workflow completed")

            reviewer_feedback = self._detailed_feedback(review_result)
            logger.warning(
                "workflow stage rejected: stage=%s attempt=%s feedback=%s",
                stage_name, attempt, reviewer_feedback,
            )
            failed_approaches.append(reviewer_feedback)
            session.state = SessionState.Rejected
            self.session_manager.increment_retry(session)
            attempt += 1

        logger.error("workflow stage exhausted retries: stage=%s attempts=%s", stage_name, attempt)
        workflow.state = self.transition.transition(WorkflowState.Failed)
        self.state_machine.fail()
        self.session_manager.close_session(session)
        message = review_result.overall_feedback if review_result else "no execution attempted"
        self._update_project_failure(project_id, stage)
        return WorkflowResult(workflow=workflow, success=False, message=message)

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

    def _record_design(self, project_id: str, stage: Stage, artifact: StageArtifact) -> None:
        """Persist an approved Designer artifact to project_id's durable design memory slot."""
        if stage != Stage.Designer:
            return
        self.memory_manager.store(project_id, _DESIGN_MEMORY_KEY, artifact.content)
        logger.debug("design artifact recorded: project_id=%s key=%s", project_id, _DESIGN_MEMORY_KEY)

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

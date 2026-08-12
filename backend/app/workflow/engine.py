"""WorkflowEngine — thin coordinator: composes single-responsibility helpers.

Each collaborator has exactly one job:
  StageRunner       — execute → review → retry loop
  ContextAssembler  — build the full prompt context for a stage
  LearningMiddleware — record trajectories, lessons, and templates
  CheckpointMiddleware — save/delete crash-recovery checkpoints
  GitMiddleware      — commit approved artifacts to git
  ProgressTracker    — compute 0-100 progress percentage

WorkflowEngine orchestrates them for one stage execution and handles
the post-approval side effects (memory recording, progress broadcast,
design persistence, sprint-plan persistence, message recording,
context-window warning).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..shared.constants import DESIGN_MEMORY_KEY, WORKFLOW_MESSAGE_KEY
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.stage import Stage
from ..shared.enums.workflow_state import WorkflowState
from ..shared.models.workflow import Workflow
from ..shared.schemas.message import AgentMessage
from .context_assembler import AssembleResult, ContextAssembler
from .middleware import CheckpointMiddleware, GitMiddleware, LearningMiddleware
from .progress_tracker import ProgressTracker
from .retry_engine import IntelligentRetryEngine
from .stage_runner import StageRunner
from .execution_state import ExecutionStateRegistry

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Runs one pipeline stage end-to-end and returns a WorkflowResult.

    Composes StageRunner + middlewares + ContextAssembler + ProgressTracker.
    Has no knowledge of the pipeline phase, sprint structure, Q&A flow,
    or requirement changes — those belong in WorkflowManager/PipelineSupervisor.
    """

    def __init__(
        self,
        stage_runner: StageRunner | None = None,
        context_assembler: ContextAssembler | None = None,
        learning_middleware: LearningMiddleware | None = None,
        checkpoint_middleware: CheckpointMiddleware | None = None,
        git_middleware: GitMiddleware | None = None,
        progress_tracker: ProgressTracker | None = None,
        # Legacy deps — kept for backward compat and container wiring
        execution_manager: Any = None,
        memory_manager: Any = None,
        learning_loop: Any = None,
        checkpoint_manager: Any = None,
        lesson_store: Any = None,
        artifact_manager: Any = None,
        workspace_manager: Any = None,
        reviewer: Any = None,
        retry_policy: Any = None,  # deprecated — superseded by retry_engine
        event_log: Any = None,
        execution_state: ExecutionStateRegistry | None = None,
        broadcaster: Any = None,
        context_orchestrator: Any = None,
        config_manager: Any = None,
        memory_orchestrator: Any = None,
        retry_engine: Any = None,
        model_router: Any = None,
        template_engine: Any = None,
    ) -> None:
        # ── Store collaborators used by post-approval helpers ──────────
        self.workspace_manager = workspace_manager
        self.memory_manager = memory_manager
        self.artifact_manager = artifact_manager
        self.memory_orchestrator = memory_orchestrator
        self.broadcaster = broadcaster
        self.execution_state = execution_state
        self.model_router = model_router

        # ── LLM settings for context-window warning ────────────────────
        from ..config.manager import ConfigurationManager
        cfg = config_manager or ConfigurationManager()
        settings = cfg.load() if hasattr(cfg, "load") else None
        self._llm_model = getattr(getattr(settings, "llm", None), "model", "") if settings else ""
        self._llm_provider = getattr(getattr(settings, "llm", None), "provider", "") if settings else ""

        # ── Build collaborators from legacy deps if not provided ───────
        if broadcaster is None:
            from ..events.broadcaster import broadcaster as default_broadcaster
            self.broadcaster = default_broadcaster

        from ..review.reviewer import Reviewer
        from ..memory.learning_loop import LearningLoop
        from ..memory.lesson_store import LessonStore
        from ..session.checkpoint import CheckpointManager
        from ..memory.manager import MemoryManager
        from ..artifact.manager import ArtifactManager
        from ..workspace.manager import WorkspaceManager
        from ..execution.manager import ExecutionManager

        _workspace = workspace_manager or WorkspaceManager()
        _artifact = artifact_manager or ArtifactManager()
        _memory = memory_manager or MemoryManager()
        _exec_mgr = execution_manager or ExecutionManager(_artifact)
        _reviewer = reviewer or Reviewer(learning_loop=learning_loop or LearningLoop())
        _retry_engine = retry_engine or IntelligentRetryEngine()
        _event_log = event_log
        if _event_log is None:
            from ..memory.project_event_log import ProjectEventLog
            _event_log = ProjectEventLog()
        _ll = learning_loop or LearningLoop()
        _ls = lesson_store or LessonStore()
        _cp = checkpoint_manager or CheckpointManager()

        self.workspace_manager = _workspace
        self.memory_manager = _memory
        self.artifact_manager = _artifact
        self.execution_manager = _exec_mgr

        # ── StageRunner ────────────────────────────────────────────────
        self._stage_runner = stage_runner or StageRunner(
            execution_manager=_exec_mgr,
            reviewer=_reviewer,
            retry_policy=retry_policy,   # forwarded as-is; only consulted when engine=None
            event_log=_event_log,
            broadcaster=self.broadcaster,
            retry_engine=_retry_engine,  # always non-None — engine is the primary gate
            execution_state=execution_state,
            artifact_manager=_artifact,
        )

        # ── ContextAssembler ───────────────────────────────────────────
        self._context_assembler = context_assembler or ContextAssembler(
            memory_orchestrator=memory_orchestrator,
            memory_manager=_memory,
            artifact_manager=_artifact,
            workspace_manager=_workspace,
            learning_loop=_ll,
            lesson_store=_ls,
            context_orchestrator=context_orchestrator,
            template_engine=template_engine,
        )

        # ── Middlewares ────────────────────────────────────────────────
        self._learning = learning_middleware or LearningMiddleware(
            learning_loop=_ll,
            lesson_store=_ls,
            template_engine=template_engine,
            llm_model=self._llm_model,
        )
        self._checkpoint = checkpoint_middleware or CheckpointMiddleware(
            checkpoint_manager=_cp,
        )
        self._git = git_middleware or GitMiddleware(workspace_manager=_workspace)

        # ── ProgressTracker ────────────────────────────────────────────
        self._progress = progress_tracker or ProgressTracker(workspace_manager=_workspace)

        # Report any incomplete sessions from prior crash.
        self._checkpoint.report_incomplete()

        # Session manager kept for session lifecycle tracking.
        from ..session.manager import SessionManager
        self.session_manager = SessionManager()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, project_id: str, stage_name: str, content: str) -> WorkflowResult:
        """Execute stage_name for project_id through the full stage lifecycle.

        Parameters
        ----------
        project_id:
            Project being built.
        stage_name:
            Canonical stage name (e.g. "Architect").
        content:
            Caller-supplied context (sprint brief, original request, etc.).
            Merged into assembled context rather than discarded.
        """
        logger.info("engine.run: project=%s stage=%s", project_id, stage_name)
        stage = Stage(stage_name)
        session = self.session_manager.create_session(stage_name)
        workflow = Workflow(
            id="", project_id=project_id, current_stage=stage,
            state=WorkflowState.Created,
        )

        # ── Apply model router profile ─────────────────────────────────
        self._apply_model_router_profile(project_id, stage_name)

        # ── Set cost-tracker context for this stage ───────────────────
        if (
            hasattr(self.execution_manager, "llm_manager")
            and self.execution_manager.llm_manager
        ):
            self.execution_manager.llm_manager.set_context(project_id, stage_name)

        # ── Assemble prompt context ────────────────────────────────────
        # assemble() returns AssembleResult(context, template_injected).
        # template_injected is forwarded to every trajectory so we can later
        # correlate injection with reviewer outcomes (P9-2b).
        assemble_result: AssembleResult = self._context_assembler.assemble(
            project_id, stage_name, content,
        )
        context = assemble_result.context
        _template_injected: bool = assemble_result.template_injected
        _injected_template_id: str | None = assemble_result.injected_template_id
        _template_similarity_score: float | None = assemble_result.template_similarity_score

        # ── Run through StageRunner with trajectory hook ───────────────
        session_id = session.session_id

        def _on_attempt(attempt: int, artifact: Any, review_result: Any) -> None:
            self._checkpoint.save(
                session_id, stage_name, project_id, attempt, [], ""
            )
            self._learning.on_attempt(
                stage_name, project_id, content, attempt, artifact, review_result,
                template_injected=_template_injected,
                injected_template_id=_injected_template_id,
                template_similarity_score=_template_similarity_score,
            )


        result = self._stage_runner.run(
            project_id, stage_name, context, on_attempt=_on_attempt,
        )

        # ── Post-run cleanup ───────────────────────────────────────────
        self._checkpoint.delete(session_id)
        self.session_manager.close_session(session)

        if result.stopped:
            self.workspace_manager.update_project_json(project_id, {"stopped": True})
            return WorkflowResult(
                workflow=workflow, success=False, message="Stopped by user", stopped=True,
            )

        if result.success and result.artifact is not None:
            artifact = result.artifact
            workflow.state = WorkflowState.Approved

            # ── Post-approval side effects ─────────────────────────────
            self._record_message(project_id, stage, artifact)
            self._record_design(project_id, stage, artifact)
            self._record_sprint_plan(project_id, stage, artifact)
            self._update_project_progress(project_id, stage)

            if self.memory_orchestrator is not None:
                struct = getattr(artifact, "structured_content", None) or {}
                self.memory_orchestrator.record_approval(project_id, stage, struct)

            self._learning.on_approval(
                stage_name, project_id, artifact,
                result.attempt_count, result.review_result, result.failed_approaches,
            )
            self._git.on_approval(project_id, stage_name, artifact)
            self.artifact_manager.mark_approved(project_id, stage, result.attempt_count)

            # Broadcast with updated progress.
            self.broadcaster.stage_complete(
                project_id, stage_name, result.attempt_count, result.duration_sec,
                progress_percent=self._progress.compute(project_id),
            )
            self._check_context_window(project_id)

            return WorkflowResult(
                workflow=workflow, success=True, message="workflow completed", artifact=artifact,
            )

        # ── Failure ────────────────────────────────────────────────────
        workflow.state = WorkflowState.Failed
        self._update_project_failure(project_id, stage)
        return WorkflowResult(workflow=workflow, success=False, message=result.message)

    # ------------------------------------------------------------------
    # Post-approval helpers
    # ------------------------------------------------------------------

    def _record_message(self, project_id: str, stage: Stage, artifact: Any) -> None:
        try:
            message = AgentMessage(
                message_id=str(uuid4()),
                role=stage.value,
                stage=stage,
                content=artifact.content,
                structured=getattr(artifact, "structured_content", None) or {},
                cause_by=getattr(artifact, "schema_type", "") or stage.value,
                sent_at=datetime.now(timezone.utc),
            )
            self.memory_manager.store(
                project_id, WORKFLOW_MESSAGE_KEY, message.model_dump_json(),
            )
        except Exception as exc:
            logger.debug("_record_message failed (non-fatal): %s", exc)

    def _record_design(self, project_id: str, stage: Stage, artifact: Any) -> None:
        if stage != Stage.Designer:
            return
        try:
            self.memory_manager.store(project_id, DESIGN_MEMORY_KEY, artifact.content)
            logger.debug("design artifact recorded: project=%s", project_id)
        except Exception as exc:
            logger.debug("_record_design failed (non-fatal): %s", exc)

    def _record_sprint_plan(self, project_id: str, stage: Stage, artifact: Any) -> None:
        if stage != Stage.SprintPlanning and stage.value not in (
            "SprintPlanning", "SprintPlanner", "Planner",
        ):
            return
        if not project_id or not artifact:
            return
        try:
            structured = getattr(artifact, "structured_content", None) or {}
            raw_content = artifact.content or "{}"
            from ..actions.base_action import BaseAction
            sprint_plan_data = structured or BaseAction.extract_json(raw_content)
            if not sprint_plan_data:
                return
            sprint_plan_data.setdefault("project_id", project_id)
            # Use explicit check rather than setdefault: the LLM often emits
            # "created_at": "" (present but empty), which setdefault leaves
            # unchanged, causing SprintPlan.model_validate to fail.
            if not sprint_plan_data.get("created_at"):
                sprint_plan_data["created_at"] = datetime.now(timezone.utc).isoformat()
            from ..shared.models.sprint import SprintPlan
            plan_model = SprintPlan.model_validate(sprint_plan_data)
            self.workspace_manager.update_sprint_plan(project_id, plan_model)
            sprint_plan_file = (
                self.workspace_manager.get_workspace_path(project_id)
                / "artifacts" / "sprint_plan.json"
            )
            sprint_plan_file.parent.mkdir(parents=True, exist_ok=True)
            sprint_plan_file.write_text(
                json.dumps(plan_model.model_dump(mode="json"), indent=2), encoding="utf-8",
            )
            logger.info(
                "sprint plan recorded: project=%s total_sprints=%s",
                project_id, plan_model.total_sprints,
            )
        except Exception as exc:
            logger.warning("_record_sprint_plan failed: %s", exc)

    def _update_project_progress(self, project_id: str, stage: Stage) -> None:
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
        if not project_id:
            return
        self.workspace_manager.update_project_json(
            project_id, {"failed_stage": stage.value},
        )

    # ------------------------------------------------------------------
    # Model router
    # ------------------------------------------------------------------

    def _apply_model_router_profile(self, project_id: str, stage_name: str) -> None:
        if self.model_router is None:
            return
        try:
            profile = self.model_router.get_profile(stage_name)
            llm = getattr(self.execution_manager, "llm_manager", None)
            if llm is not None and hasattr(llm, "set_stage_profile"):
                llm.set_stage_profile(profile)
        except Exception as exc:
            logger.debug("_apply_model_router_profile skipped: %s", exc)

    # ------------------------------------------------------------------
    # Context-window warning
    # ------------------------------------------------------------------

    _CONTEXT_LIMITS: dict[str, int] = {
        "claude": 200_000,
        "bedrock": 200_000,
        "gemini": 1_000_000,
        "openai": 128_000,
        "ollama": 32_000,
    }
    _CONTEXT_WARNING_THRESHOLD = 0.75

    def _check_context_window(self, project_id: str) -> None:
        try:
            from ..llm.cost_tracker import get_shared_cost_tracker
            tracker = get_shared_cost_tracker()
            cost = tracker.get_project_cost(project_id)
            used_tokens = cost.total_tokens
            if used_tokens == 0:
                return
            provider = (self._llm_provider or "").lower().strip()
            if provider not in self._CONTEXT_LIMITS:
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
                    "context window %d%% full: project=%s used=%d limit=%d",
                    pct, project_id, used_tokens, limit,
                )
                self.broadcaster.context_warning(
                    project_id=project_id,
                    used_tokens=used_tokens,
                    limit_tokens=limit,
                    pct=pct,
                )
        except Exception as exc:
            logger.debug("_check_context_window failed (non-fatal): %s", exc)

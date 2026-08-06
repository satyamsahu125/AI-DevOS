from __future__ import annotations

import json
import logging
from typing import Any

from ..shared.dto.stage_context import StageContext
from ..shared.enums.stage import Stage

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    """Unified memory access layer for WorkflowEngine.

    Assembles all four memory layers into a single typed StageContext:
      Layer 1 (Working)    — in-process, assembled here from layers below
      Layer 2 (Episodic)   — per-stage approved outputs via MemoryManager
      Layer 3 (Semantic)   — cross-project lessons + patterns via ContextManager
      Layer 4 (Procedural) — live project intelligence via ContextOrchestrator

    Replaces the six ad-hoc _with_*() methods in WorkflowEngine. All context
    assembly is in one place with a defined error contract: get_context() never
    raises — failed layers log a warning and return empty data.
    """

    def __init__(
        self,
        memory_manager: Any = None,
        artifact_manager: Any = None,
        workspace_manager: Any = None,
        context_manager: Any = None,
        context_orchestrator: Any = None,
        learning_loop: Any = None,
        lesson_store: Any = None,
    ) -> None:
        self.memory_manager = memory_manager
        self.artifact_manager = artifact_manager
        self.workspace_manager = workspace_manager
        self.context_manager = context_manager          # Layer 3 (Semantic)
        self.context_orchestrator = context_orchestrator  # Layer 4 (Procedural)
        self.learning_loop = learning_loop              # Phase 7: approved trajectory recording
        self.lesson_store = lesson_store                # Phase 7: rejection lesson recording

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self, project_id: str, stage: Stage) -> StageContext:
        """Build a complete StageContext for stage, assembling all memory layers.

        Never raises. If any layer fails, it logs a warning and contributes
        empty data to the returned context.
        """
        logger.info("memory_orchestrator.get_context: project=%s stage=%s", project_id, stage.value)

        ctx = StageContext(project_id=project_id, stage=stage)

        # --- Layer 2: Episodic — load original request and per-stage outputs ---
        ctx.original_request = self._load_original_request(project_id)
        ctx.clarification = self._load_artifact_struct(project_id, Stage.Clarification)
        ctx.strategic_brief = self._load_artifact_struct(project_id, Stage.StrategicReview)
        ctx.domain_research = self._load_artifact_struct(project_id, Stage.DomainResearch)
        ctx.design_artifact = self._load_artifact_struct(project_id, Stage.Designer)
        ctx.architecture_artifact = self._load_artifact_struct(project_id, Stage.Architect)
        ctx.predecessor_outputs = self._load_predecessor_outputs(project_id, stage)

        # Bug B defence: if clarification is still empty after artifact load,
        # build a minimal context from project.json so ProductOwner always has
        # something meaningful for its PRIMARY input.
        if not ctx.clarification and stage == Stage.ProductOwner:
            ctx.clarification = self._build_minimal_clarification(
                project_id, ctx.original_request
            )
            logger.warning(
                "memory_orchestrator: no Clarification artifact for %s at ProductOwner — "
                "using minimal fallback built from original_request",
                project_id,
            )

        # --- Layer 3: Semantic — lessons + cross-project patterns ---
        ctx.lessons, ctx.patterns = self._load_semantic(project_id, stage)

        # --- Layer 4: Procedural — project intelligence ---
        ctx.intelligence = self._load_intelligence(project_id)

        logger.debug(
            "memory_orchestrator.get_context complete: project=%s stage=%s "
            "clarification_keys=%s lessons=%d patterns=%d intelligence=%s",
            project_id, stage.value,
            list((ctx.clarification or {}).keys())[:5],
            len(ctx.lessons), len(ctx.patterns),
            "populated" if ctx.intelligence else "empty",
        )
        return ctx

    def record_approval(self, project_id: str, stage: Stage, artifact: dict) -> None:
        """Called after a stage is approved. Persists to episodic memory and learning loop.

        Also schedules semantic indexing (non-blocking — failures are logged).
        """
        logger.info("memory_orchestrator.record_approval: project=%s stage=%s", project_id, stage.value)
        if self.memory_manager:
            try:
                self.memory_manager.store_stage_output(
                    project_id, stage.value, json.dumps(artifact, indent=2)
                )
            except Exception as exc:
                logger.warning("record_approval: memory write failed for %s/%s: %s", project_id, stage.value, exc)

        # Phase 7: record approved trajectory into LearningLoop so future stages can
        # retrieve semantic patterns from what worked in similar past runs.
        if self.learning_loop:
            try:
                summary = json.dumps(artifact, indent=2)[:500]  # trim large artifacts
                self.learning_loop.record_success(
                    stage=stage.value,
                    task_description=f"Stage {stage.value} approved",
                    artifact_summary=summary,
                    project_id=project_id,
                )
            except Exception as exc:
                logger.warning("record_approval: learning_loop write failed for %s/%s: %s", project_id, stage.value, exc)

    def record_rejection(self, project_id: str, stage: Stage, feedback: Any) -> None:
        """Called after a stage is rejected. Records the attempt for learning and lesson store."""
        logger.info("memory_orchestrator.record_rejection: project=%s stage=%s", project_id, stage.value)
        if self.memory_manager:
            try:
                rejection_entry = {
                    "stage": stage.value,
                    "feedback": str(feedback),
                }
                self.memory_manager.store(
                    project_id,
                    f"workflow:rejection:{stage.value}",
                    json.dumps(rejection_entry),
                )
            except Exception as exc:
                logger.warning("record_rejection: memory write failed for %s/%s: %s", project_id, stage.value, exc)

        # Phase 7: record rejection lesson into LessonStore so future runs at the same
        # stage can retrieve what failed and avoid repeating it.
        if self.lesson_store:
            try:
                self.lesson_store.record(
                    stage=stage.value,
                    project_id=project_id,
                    what_worked="",
                    what_failed=str(feedback),
                    reviewer_said=str(feedback),
                    retry_count=0,
                )
            except Exception as exc:
                logger.warning("record_rejection: lesson_store write failed for %s/%s: %s", project_id, stage.value, exc)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_original_request(self, project_id: str) -> str:
        if self.workspace_manager:
            try:
                p_data = self.workspace_manager.load_project_json(project_id) or {}
                return p_data.get("original_request") or p_data.get("description") or ""
            except Exception as exc:
                logger.warning("_load_original_request failed for %s: %s", project_id, exc)
        return ""

    def _load_artifact_struct(self, project_id: str, stage: Stage) -> dict | None:
        if not self.artifact_manager:
            return None
        try:
            artifact = self.artifact_manager.get_artifact(project_id, stage)
            if artifact is None:
                return None
            return getattr(artifact, "structured_content", None) or {}
        except Exception as exc:
            logger.warning("_load_artifact_struct failed for %s/%s: %s", project_id, stage.value, exc)
            return None

    def _load_predecessor_outputs(self, project_id: str, stage: Stage) -> dict[str, Any]:
        """Load all previously approved stage outputs from episodic memory."""
        outputs: dict[str, Any] = {}
        if not self.memory_manager:
            return outputs
        all_stages = [s for s in Stage]
        for s in all_stages:
            if s == stage:
                break
            try:
                raw = self.memory_manager.load_stage_output(project_id, s.value)
                if raw:
                    try:
                        outputs[s.value] = json.loads(raw)
                    except json.JSONDecodeError:
                        outputs[s.value] = raw
            except Exception as exc:
                logger.debug("_load_predecessor_outputs: skipped %s: %s", s.value, exc)
        return outputs

    def _build_minimal_clarification(self, project_id: str, original_request: str) -> dict:
        return {
            "original_request": original_request,
            "project_description": original_request,
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
                "Infer full scope and requirements from the original_request above."
            ),
        }

    def _load_semantic(self, project_id: str, stage: Stage) -> tuple[list[str], list[str]]:
        """Load lessons and patterns from the semantic memory layer (ContextManager)."""
        lessons: list[str] = []
        patterns: list[str] = []
        if not self.context_manager:
            return lessons, patterns
        try:
            agent_ctx = self.context_manager.build_context(project_id, stage.value)
            lessons = getattr(agent_ctx, "lessons", []) or []
            patterns = list(getattr(agent_ctx, "past_patterns", []) or [])
            patterns += list(getattr(agent_ctx, "cross_project_patterns", []) or [])
        except Exception as exc:
            logger.warning("_load_semantic failed for %s/%s: %s", project_id, stage.value, exc)
        return lessons, patterns

    def _load_intelligence(self, project_id: str) -> dict:
        """Load procedural memory from the intelligence layer.

        Always returns a dict — never None. Returns {} if unavailable.
        Calls context_orchestrator.get_project_state() which itself never
        returns None (Phase 3, item 3.2 contract).
        """
        if not self.context_orchestrator:
            return {}
        try:
            state = self.context_orchestrator.get_project_state(project_id)
            if not isinstance(state, dict):
                return {"data": str(state)} if state is not None else {}
            return state
        except Exception as exc:
            logger.warning("_load_intelligence failed for %s: %s", project_id, exc)
            return {}

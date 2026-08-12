"""LearningMiddleware — trajectory recording, lesson extraction, template extraction.

Single responsibility: after every stage attempt (approved or rejected),
record what happened so future runs can learn from it.

Three sub-tasks live here because they all answer the same question
("what happened on this attempt?") and share the same data sources.
They are not split further because separating them would require passing
the same attempt data through three independent hooks with no benefit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...memory.lesson_store import Lesson, new_lesson_id
from ...memory.learning_loop import Trajectory

logger = logging.getLogger(__name__)


class LearningMiddleware:
    """Records trajectories, extracts lessons, and saves structural templates.

    Called by WorkflowEngine:
      - on_attempt(attempt, artifact, review_result) — after every attempt
      - on_approval(stage_name, project_id, artifact, attempt,
                    review_result, failed_approaches) — only on approval
    """

    def __init__(
        self,
        learning_loop: Any,
        lesson_store: Any,
        template_engine: Any = None,
        llm_model: str = "",
    ) -> None:
        self.learning_loop = learning_loop
        self.lesson_store = lesson_store
        self.template_engine = template_engine
        self._llm_model = llm_model
        self._last_trajectory_ids: dict[tuple[str, str], str] = {}
        self._last_trajectory_id: str | None = None

    # ------------------------------------------------------------------
    # Hooks called by WorkflowEngine
    # ------------------------------------------------------------------

    def on_attempt(
        self,
        stage_name: str,
        project_id: str,
        content: str,
        attempt: int,
        artifact: Any,
        review_result: Any,
        template_injected: bool = False,
        injected_template_id: str | None = None,
        template_similarity_score: float | None = None,
    ) -> None:
        """Record a Trajectory (approved or rejected) after every attempt.

        Parameters
        ----------
        template_injected:
            Set to True when ContextAssembler injected a structural template
            hint into the context for this attempt.
        injected_template_id:
            The exact template_id injected for this attempt (P9-2b Phase B).
        template_similarity_score:
            Similarity score if computed, or None (P9-2b Phase B).
        """
        if not hasattr(self, "_last_trajectory_ids") or self._last_trajectory_ids is None:
            self._last_trajectory_ids = {}
        self._last_trajectory_ids.pop((project_id, stage_name), None)
        self._last_trajectory_id = None

        try:
            from ...llm.cost_tracker import get_shared_cost_tracker
            tracker = get_shared_cost_tracker()
            trajectory = Trajectory(
                stage=stage_name,
                task_description=content,
                artifact_summary=(artifact.content or "")[:300],
                retry_count=attempt,
                approved=review_result.approved,
                reviewer_feedback=review_result.overall_feedback,
                agent_model=self._llm_model,
                tokens_used=tracker.last_call_tokens,
                latency_ms=tracker.last_call_latency,
                project_id=project_id,
                template_injected=template_injected,
                injected_template_id=injected_template_id,
                template_similarity_score=template_similarity_score,
            )
            traj_id = self.learning_loop.record_trajectory(trajectory)
            if traj_id is not None:
                tid_str = str(traj_id)
                self._last_trajectory_ids[(project_id, stage_name)] = tid_str
                self._last_trajectory_id = tid_str
        except Exception as exc:
            logger.debug("LearningMiddleware.on_attempt failed (non-fatal): %s", exc)

    def on_approval(
        self,
        stage_name: str,
        project_id: str,
        artifact: Any,
        attempt: int,
        review_result: Any,
        failed_approaches: list[str],
    ) -> None:
        """Extract a Lesson and a structural template on approval."""
        self._record_lesson(stage_name, project_id, artifact, attempt,
                            review_result, failed_approaches)
        trajectory_ids = getattr(self, "_last_trajectory_ids", None)
        if trajectory_ids is not None and (project_id, stage_name) in trajectory_ids:
            orig_traj_id = trajectory_ids.get((project_id, stage_name))
        else:
            orig_traj_id = getattr(self, "_last_trajectory_id", None)
        self._extract_template(stage_name, project_id, artifact, originating_trajectory_id=orig_traj_id)



    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_lesson(
        self,
        stage_name: str,
        project_id: str,
        artifact: Any,
        attempt: int,
        review_result: Any,
        failed_approaches: list[str],
    ) -> None:
        try:
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
        except Exception as exc:
            logger.debug("LearningMiddleware._record_lesson failed (non-fatal): %s", exc)

    def _extract_template(
        self,
        stage_name: str,
        project_id: str,
        artifact: Any,
        originating_trajectory_id: str | None = None,
    ) -> None:
        if self.template_engine is None:
            return
        try:
            struct = getattr(artifact, "structured_content", None) or {}
            if struct:
                self.template_engine.extract_template(
                    struct, stage_name, project_id, originating_trajectory_id=originating_trajectory_id,
                )
                logger.debug(
                    "template extracted: stage=%s project=%s orig_traj=%s",
                    stage_name, project_id, originating_trajectory_id,
                )
        except Exception as exc:
            logger.debug("LearningMiddleware._extract_template failed (non-fatal): %s", exc)


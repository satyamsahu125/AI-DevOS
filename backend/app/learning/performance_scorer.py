from __future__ import annotations

import json
import logging
from typing import Any

from ..llm.cost_tracker import CostTracker
from ..memory.learning_loop import LearningLoop

logger = logging.getLogger(__name__)


class AgentPerformanceScorer:
    """Computes quality scores for each agent based on retry rate, success rate, and token usage."""

    def __init__(
        self,
        learning_loop: LearningLoop | None = None,
        cost_tracker: CostTracker | None = None,
        memory_manager: Any | None = None,
    ) -> None:
        if learning_loop is not None:
            self.learning_loop = learning_loop
        else:
            from ..memory.learning_loop import LearningLoop as DefaultLL

            self.learning_loop = DefaultLL()
        if cost_tracker is not None:
            self.cost_tracker = cost_tracker
        else:
            from ..llm.cost_tracker import get_shared_cost_tracker

            self.cost_tracker = get_shared_cost_tracker()
        # memory_manager is optional — used to persist scores for IntelligentRetryEngine
        self.memory_manager = memory_manager

    def score_agent(self, stage: str, project_id: str | None = None) -> dict[str, Any]:
        """Score an agent's performance on a stage. Returns scores from 0.0 to 1.0."""
        perf = self.learning_loop.get_agent_performance(stage)

        if hasattr(perf, "total"):
            total = getattr(perf, "total", 0)
            avg_retries = getattr(perf, "avg_retries", 0.0)
            success_score = getattr(perf, "success_rate", 0.0)
        elif isinstance(perf, dict):
            total = perf.get("total", 0)
            avg_retries = perf.get("avg_retries", 0.0)
            success_score = perf.get("success_rate", 0.0)
        else:
            total = 0
            avg_retries = 0.0
            success_score = 0.0

        if total == 0:
            return {
                "stage": stage,
                "score": None,
                "message": "No data yet — run more projects",
                "total_runs": 0,
            }

        retry_score = max(0.0, 1.0 - (avg_retries / 2.0))
        composite = (retry_score * 0.6) + (success_score * 0.4)

        quality = (
            "excellent"
            if composite >= 0.85
            else "good"
            if composite >= 0.70
            else "fair"
            if composite >= 0.50
            else "needs_improvement"
        )

        result = {
            "stage": stage,
            "score": round(composite, 3),
            "quality": quality,
            "retry_score": round(retry_score, 3),
            "success_score": round(success_score, 3),
            "avg_retries": round(avg_retries, 2),
            "total_runs": total,
            "recommendation": self._recommendation(quality, avg_retries),
        }
        # Persist score to memory so IntelligentRetryEngine can read it without
        # querying the LearningLoop on every decision (avoids repeated DB round-trips).
        if self.memory_manager is not None:
            try:
                _project_key = project_id or "__global__"
                self.memory_manager.store(
                    _project_key,
                    f"perf:score:{stage}",
                    json.dumps(result),
                )
            except Exception as exc:
                logger.debug("score_agent: memory write skipped for %s/%s: %s", project_id, stage, exc)
        return result

    def score_all_agents(self) -> list[dict[str, Any]]:
        """Score all known stages."""
        stages = [
            "strategic_review",
            "product_owner",
            "architect",
            "designer",
            "security",
            "sprint_planner",
            "scrum_master",
            "file_planner",
            "backend",
            "frontend",
            "qa",
            "document",
            "devops",
            "retro",
        ]
        scores = []
        for stage in stages:
            score = self.score_agent(stage)
            if score.get("total_runs", 0) > 0:
                scores.append(score)

        return sorted(scores, key=lambda s: s.get("score", 1.0) if s.get("score") is not None else 1.0)

    def _recommendation(self, quality: str, avg_retries: float) -> str:
        if quality == "excellent":
            return "Performing well — no changes needed"
        if quality == "good":
            return "Minor prompt improvements possible"
        if avg_retries > 1.5:
            return (
                "High retry rate — reviewer is rejecting output. Prompt needs clearer output format instructions."
            )
        return "Low success rate — check schema validation and prompt specificity."

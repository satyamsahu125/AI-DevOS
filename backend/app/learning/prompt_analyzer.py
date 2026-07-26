from __future__ import annotations

import logging
from typing import Any

from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.lesson_store import LessonStore

logger = logging.getLogger(__name__)


class PromptQualityAnalyzer:
    """Analyzes what makes agent prompts succeed or fail by reading LessonStore and KnowledgeMemory."""

    def __init__(
        self,
        lesson_store: LessonStore | None = None,
        knowledge_memory: KnowledgeMemory | None = None,
    ) -> None:
        self.lessons = lesson_store
        self.knowledge = knowledge_memory

    def analyze_stage(self, stage: str, top_k: int = 10) -> dict[str, Any]:
        """Analyze lessons and past successes for a stage. Returns actionable insights."""
        lessons = []
        if self.lessons is not None:
            try:
                lessons = self.lessons.get_all_lessons(stage=stage, limit=top_k)
            except Exception as exc:
                logger.debug("Failed loading lessons for stage %s: %s", stage, exc)

        if not lessons:
            return {
                "stage": stage,
                "insights": [],
                "common_failures": [],
                "what_works": [],
                "message": "No lessons yet for this stage",
            }

        what_works = [
            l.what_worked for l in lessons if l.what_worked and len(l.what_worked) > 10
        ]
        what_fails = [
            l.what_failed for l in lessons if l.what_failed and len(l.what_failed) > 10
        ]
        reviewer_said = [
            l.reviewer_said for l in lessons if l.reviewer_said and len(l.reviewer_said) > 10
        ]

        insights = self._extract_patterns(what_works, what_fails, reviewer_said, stage)

        return {
            "stage": stage,
            "lessons_analyzed": len(lessons),
            "what_works": what_works[:3],
            "common_failures": what_fails[:3],
            "reviewer_patterns": reviewer_said[:3],
            "insights": insights,
        }

    def _extract_patterns(
        self,
        works: list[str],
        fails: list[str],
        reviewer: list[str],
        stage: str,
    ) -> list[str]:
        """Extract actionable patterns from lessons."""
        insights = []

        if len(fails) > 0:
            insights.append(f"Stage '{stage}' commonly fails on: {fails[0][:80]}")
        if len(works) > 0:
            insights.append(f"What works for '{stage}': {works[0][:80]}")
        if len(reviewer) > 0:
            insights.append(f"Reviewer often says for '{stage}': {reviewer[0][:80]}")

        return insights

    def get_cross_project_patterns(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Semantic search across all past successful patterns for a given type of task."""
        if self.knowledge is None:
            return []

        try:
            results = self.knowledge.search(query=query, top_k=top_k)
        except Exception as exc:
            logger.debug("Failed searching patterns for query %s: %s", query, exc)
            results = []

        out = []
        for r in results:
            score = getattr(r, "score", 0.0) if not isinstance(r, dict) else r.get("score", 0.0)
            val = getattr(r, "value", "") if not isinstance(r, dict) else r.get("value", "")
            cat = getattr(r, "category", "") if not isinstance(r, dict) else r.get("category", "")
            if score > 0.6:
                out.append({
                    "score": score,
                    "content": str(val)[:300],
                    "category": cat,
                })
        return out

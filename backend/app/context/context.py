from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from ..memory.learning_loop import LearningLoop
from ..memory.lesson_store import LessonStore
from ..memory.manager import MemoryManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentContext:
    """Immutable-in-practice payload handed to an agent for exactly one execution."""

    project_name: str = ""
    requirements: str = ""
    architecture: str = ""
    agent_name: str = ""
    task: str = ""
    memory: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    past_patterns: list[str] = field(default_factory=list)
    agent_performance: dict[str, Any] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    additional_context: str = ""
    cross_project_patterns: list[str] = field(default_factory=list)


class ContextManager:
    """Builds the context an agent needs for one stage execution."""

    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        learning_loop: LearningLoop | None = None,
        lesson_store: LessonStore | None = None,
        workspace_manager: Any | None = None,
        prompt_analyzer: Any | None = None,
    ) -> None:
        """Wire the MemoryManager, LearningLoop, and LessonStore used to load context."""
        self.memory_manager = memory_manager or MemoryManager()
        self.learning_loop = learning_loop or LearningLoop()
        self.lesson_store = lesson_store or LessonStore()
        self.prompt_analyzer = prompt_analyzer
        if workspace_manager is not None:
            self.workspace = workspace_manager
        else:
            from ..workspace.manager import WorkspaceManager
            self.workspace = WorkspaceManager()

    def build(self, request: str, **kwargs: Any) -> dict[str, Any]:
        """Build a raw context dict (kept for existing callers of the documented interface)."""
        return {"request": request, **kwargs}

    def build_context(self, project_id: str, stage_name: str, task: str = "") -> AgentContext:
        """Build an AgentContext for stage_name, loading relevant memory for project_id."""
        logger.info("building context: project_id=%s stage=%s", project_id, stage_name)
        memory_entries: list[str] = []

        project_entry = self.memory_manager.load(project_id, "project")
        if project_entry:
            memory_entries.append(project_entry)

        workflow_entry = self.memory_manager.load(project_id, "workflow")
        if workflow_entry:
            memory_entries.append(workflow_entry)

        review_entry = self.memory_manager.load(project_id, f"review:{stage_name}")
        if review_entry:
            memory_entries.append(review_entry)

        pj = self.workspace.load_project_json(project_id) or {}
        project_name = pj.get("name") or pj.get("title") or project_id
        changes = pj.get("requirement_changes", [])

        change_context = ""
        if changes:
            recent = changes[-3:]  # last 3 changes
            change_context = "\n\nREQUIREMENT CHANGES APPLIED:\n"
            for c in recent:
                change_context += (
                    f"  - {c.get('description', '')}"
                    + (f" (context: {c['comment']})" if c.get("comment") else "")
                    + "\n"
                )
            change_context += "Incorporate these changes in your output."
            memory_entries.append(change_context)

        logger.debug("context memory loaded: project_id=%s entries=%s", project_id, len(memory_entries))

        resolved_task = task or stage_name
        patterns = self.learning_loop.get_relevant_patterns(resolved_task, stage_name)
        performance = asdict(self.learning_loop.get_agent_performance(stage_name))
        logger.debug("learning loop loaded: stage=%s patterns=%s", stage_name, len(patterns))

        lessons = self.lesson_store.get_lessons(stage_name, project_id)
        lesson_summaries = [f"Worked: {lesson.what_worked[:120]} | Failed: {lesson.what_failed[:120]}" for lesson in lessons]
        logger.debug("lesson store loaded: stage=%s project_id=%s lessons=%s", stage_name, project_id, len(lesson_summaries))

        cross_project_patterns: list[str] = []
        try:
            analyzer = self.prompt_analyzer
            if analyzer is None:
                from ..learning.prompt_analyzer import PromptQualityAnalyzer
                analyzer = PromptQualityAnalyzer()
            search_results = analyzer.get_cross_project_patterns(query=f"{stage_name}: {resolved_task[:100]}", top_k=3)
            cross_project_patterns = [p["content"] for p in search_results if p.get("score", 0.0) > 0.65]
        except Exception as exc:
            logger.debug("Pattern injection skipped: %s", exc)

        return AgentContext(
            project_name=project_name,
            agent_name=stage_name,
            task=resolved_task,
            memory=memory_entries,
            past_patterns=patterns,
            agent_performance=performance,
            lessons=lesson_summaries,
            additional_context=change_context,
            cross_project_patterns=cross_project_patterns,
        )


class ContextBuilder(ContextManager):
    """Backward-compatible alias for the context manager."""

    pass

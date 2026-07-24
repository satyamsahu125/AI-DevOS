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


class ContextManager:
    """Builds the context an agent needs for one stage execution.

    build_context() is the documented entry point: it loads whatever
    project, workflow, and review memory is available for the given
    project/stage, plus LearningLoop's relevant past patterns and this
    stage's performance stats, plus LessonStore's human-readable lessons,
    and returns it all as part of the AgentContext, so agents never query
    MemoryManager/LearningLoop/LessonStore directly.
    """

    def __init__(
        self,
        memory_manager: MemoryManager | None = None,
        learning_loop: LearningLoop | None = None,
        lesson_store: LessonStore | None = None,
    ) -> None:
        """Wire the MemoryManager, LearningLoop, and LessonStore used to load context."""
        self.memory_manager = memory_manager or MemoryManager()
        self.learning_loop = learning_loop or LearningLoop()
        self.lesson_store = lesson_store or LessonStore()

    def build(self, request: str, **kwargs: Any) -> dict[str, Any]:
        """Build a raw context dict (kept for existing callers of the documented interface)."""
        return {"request": request, **kwargs}

    def build_context(self, project_id: str, stage_name: str, task: str = "") -> AgentContext:
        """Build an AgentContext for stage_name, loading relevant memory for project_id.

        Loads, in order: project memory, workflow-state memory, and past
        review feedback for this stage -- each stored under its own
        namespaced key in MemoryManager -- and includes whatever is found
        in AgentContext.memory. Also loads LearningLoop's semantically
        relevant past patterns and this stage's performance stats, plus
        LessonStore's human-readable lessons for this project/stage.
        """
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

        logger.debug("context memory loaded: project_id=%s entries=%s", project_id, len(memory_entries))

        resolved_task = task or stage_name
        patterns = self.learning_loop.get_relevant_patterns(resolved_task, stage_name)
        performance = asdict(self.learning_loop.get_agent_performance(stage_name))
        logger.debug("learning loop loaded: stage=%s patterns=%s", stage_name, len(patterns))

        lessons = self.lesson_store.get_lessons(stage_name, project_id)
        lesson_summaries = [f"Worked: {lesson.what_worked[:120]} | Failed: {lesson.what_failed[:120]}" for lesson in lessons]
        logger.debug("lesson store loaded: stage=%s project_id=%s lessons=%s", stage_name, project_id, len(lesson_summaries))

        return AgentContext(
            project_name=project_id,
            agent_name=stage_name,
            task=resolved_task,
            memory=memory_entries,
            past_patterns=patterns,
            agent_performance=performance,
            lessons=lesson_summaries,
        )


class ContextBuilder(ContextManager):
    """Backward-compatible alias for the context manager."""

    pass

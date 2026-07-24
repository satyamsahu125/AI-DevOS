from fastapi import APIRouter, Depends

from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.learning_loop import LearningLoop
from ..memory.lesson_store import LessonStore
from ..memory.manager import MemoryManager
from .dependencies import get_knowledge_memory, get_learning_loop, get_memory_manager

router = APIRouter()


@router.get("/memory/{project_id}")
def get_project_memory(
    project_id: str,
    memory_manager: MemoryManager = Depends(get_memory_manager),
    learning_loop: LearningLoop = Depends(get_learning_loop),
    knowledge_memory: KnowledgeMemory = Depends(get_knowledge_memory),
) -> dict:
    """Inspect every memory record namespaced under project_id, plus lesson/trajectory/knowledge counts.

    trajectory_count and knowledge_entry_count are global (across every
    project), not project-scoped: the underlying trajectories/knowledge
    tables don't carry a project_id column (see LearningLoop.count_all_trajectories).
    """
    records = [
        {
            "key": record.title.removeprefix(f"{project_id}:"),
            "value_preview": record.content[:200],
            "stored_at": record.updated_at.isoformat(),
        }
        for record in memory_manager.list_for_project(project_id)
    ]

    lesson_store = LessonStore()

    return {
        "project_id": project_id,
        "records": records,
        "lesson_count": lesson_store.count_for_project(project_id),
        "trajectory_count": learning_loop.count_all_trajectories(),
        "knowledge_entry_count": knowledge_memory.count_all(),
    }

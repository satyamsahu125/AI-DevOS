from fastapi import APIRouter, Depends

from ..memory.knowledge_memory import KnowledgeMemoryFactory
from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.learning_loop import LearningLoop
from ..memory.lesson_store import LessonStore
from ..memory.manager import MemoryManager
from .dependencies import get_knowledge_memory, get_learning_loop, get_memory_manager

router = APIRouter()


@router.get("/memory/stats")
def get_memory_stats() -> dict:
    """Return a live snapshot of the KnowledgeMemoryFactory state.

    This endpoint does NOT require a project_id — it reflects the
    factory-level view across all in-memory project instances.

    Response fields
    ---------------
    total_projects_in_memory : int
        Number of per-project KnowledgeMemory instances currently loaded
        in the process-level cache.
    total_entries : int
        Sum of knowledge entries across all in-memory project stores.
    largest_project : dict | None
        ``{"project_id": str, "entries": int}`` for the project with the
        most entries, or null if no projects are loaded.
    inactive_project_count : int
        Number of project directories on disk that are NOT currently
        in-memory (i.e. evicted or never loaded in this process).
    """
    return KnowledgeMemoryFactory.stats()


@router.post("/memory/archive")
def archive_inactive_projects(days: int = 30) -> dict:
    """Move project knowledge stores inactive for ``days`` days to the archive directory.

    Data is NEVER deleted — projects are moved to
    ``<DATA_DIR>/archive/<project_id>/`` and can be restored manually.

    Query parameters
    ----------------
    days : int (default 30)
        Projects whose on-disk directory has not been modified in this
        many days are considered inactive and will be archived.

    Response fields
    ---------------
    archived : list[str]
        Project IDs that were archived during this call.
    archived_count : int
        Convenience count of the archived list.
    days : int
        The inactivity threshold used for this call.
    """
    archived = KnowledgeMemoryFactory.archive_inactive(days=days)
    return {
        "archived": archived,
        "archived_count": len(archived),
        "days": days,
    }


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

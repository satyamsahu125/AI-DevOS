from fastapi import APIRouter, Depends

from ..llm.cost_tracker import get_shared_cost_tracker
from ..memory.project_event_log import ProjectEventLog
from .dependencies import get_event_log

router = APIRouter()


@router.get("/projects/{project_id}/logs")
def get_project_logs(
    project_id: str, since_id: int = 0, event_log: ProjectEventLog = Depends(get_event_log),
) -> list[dict]:
    """Return project_id's real build events with id > since_id, oldest first.

    Poll this with the last event's id as the next call's since_id to fetch
    only what's new -- the standard log-tailing pattern.
    """
    return [
        {
            "id": event.id,
            "stage": event.stage,
            "level": event.level,
            "message": event.message,
            "created_at": event.created_at.isoformat(),
        }
        for event in event_log.get_events(project_id, since_id=since_id)
    ]


@router.get("/projects/{project_id}/cost")
def get_project_cost(project_id: str) -> dict:
    """Return project_id's aggregated LLM token/latency usage across every stage so far."""
    summary = get_shared_cost_tracker().get_project_cost(project_id)
    return {
        "project_id": project_id,
        "calls": summary.calls,
        "prompt_tokens": summary.prompt_tokens,
        "completion_tokens": summary.completion_tokens,
        "total_tokens": summary.total_tokens,
        "total_latency_ms": summary.total_latency_ms,
    }

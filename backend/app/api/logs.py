from fastapi import APIRouter, Depends

from ..llm.cost_tracker import PRICING_LAST_UPDATED, get_shared_cost_tracker
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
    """Return project_id's LLM token/latency usage.

    Returns both a backward-compatible aggregate block AND a full per-stage
    breakdown (same data as /projects/{project_id}/metrics) so the Metrics tab
    can show per-stage cost breakdowns without a second API call.
    """
    tracker = get_shared_cost_tracker()
    # Aggregate (legacy)
    agg = tracker.get_project_cost(project_id)
    # Full per-stage summary with estimated USD cost
    full = tracker.get_project_summary(project_id)
    return {
        # ── Aggregate (legacy callers) ───────────────────────────────────
        "project_id": project_id,
        "calls": agg.calls,
        "prompt_tokens": agg.prompt_tokens,
        "completion_tokens": agg.completion_tokens,
        "total_tokens": agg.total_tokens,
        "total_latency_ms": agg.total_latency_ms,
        # ── Detailed breakdown (new) ─────────────────────────────────────
        "estimated_cost_usd": full.estimated_cost_usd,
        "most_expensive_stage": full.most_expensive_stage,
        "slowest_stage": full.slowest_stage,
        "total_latency_seconds": full.total_latency_seconds,
        "pricing_last_updated": PRICING_LAST_UPDATED,
        "stages": [
            {
                "stage": s.stage,
                "llm_calls": s.llm_calls,
                "prompt_tokens": s.prompt_tokens,
                "completion_tokens": s.completion_tokens,
                "total_tokens": s.total_tokens,
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "total_latency_ms": round(s.total_latency_ms, 1),
                "success_rate": round(s.success_rate, 3),
                "retries": s.retries,
            }
            for s in full.stages
        ],
    }

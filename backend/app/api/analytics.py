"""R7 — Analytics API.

Surfaces the data already collected by CostTracker, LearningLoop, and
LessonStore. All endpoints are read-only — no project-state mutation.

Endpoints:
  GET /analytics/overview            — global system stats
  GET /analytics/projects/{id}       — per-project cost and stage breakdown
  GET /analytics/stage/{stage_name}  — per-stage performance stats + failure patterns
  GET /analytics/learning            — aggregated lessons from LessonStore
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from ..llm.cost_tracker import get_shared_cost_tracker, TOKEN_COST_PER_1K

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


def _get_learning_loop():
    """Lazy-resolve LearningLoop from DI container — avoids circular imports at module load."""
    from ..kernel.container import container
    try:
        return container.resolve("learning_loop")
    except Exception:
        return None


def _get_lesson_store():
    """Lazy-resolve LessonStore from DI container."""
    from ..kernel.container import container
    try:
        return container.resolve("lesson_store")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# GET /analytics/overview
# ---------------------------------------------------------------------------

@router.get("/api/analytics/overview")
@router.get("/analytics/overview")
async def get_overview() -> dict[str, Any]:
    """System-wide analytics overview.

    Aggregates across all projects:
    - Total tokens / cost / calls
    - Most expensive stage (by total tokens)
    - Stage success rates from LearningLoop trajectories
    """
    tracker = get_shared_cost_tracker()

    # Global cost totals from CostTracker
    total_summary = tracker.get_total()
    total_calls = total_summary.calls
    total_tokens = total_summary.total_tokens
    total_latency_ms = total_summary.total_latency_ms

    # Per-stage totals via direct SQLite query for efficiency
    try:
        rows = tracker._conn.execute(
            """
            SELECT stage,
                   COUNT(*) as calls,
                   SUM(total_tokens) as tokens,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   AVG(latency_ms) as avg_latency,
                   SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
                   model
            FROM llm_calls
            GROUP BY stage
            ORDER BY tokens DESC
            """
        ).fetchall()
    except Exception as exc:
        logger.warning("[analytics] stage query failed: %s", exc)
        rows = []

    stage_stats: dict[str, dict] = {}
    most_expensive_stage = "none"
    most_expensive_tokens = 0
    all_models: dict[str, int] = {}

    for row in rows:
        stage, calls, tokens, pt, ct, avg_lat, successes, model = row
        tokens = tokens or 0
        calls = calls or 0
        if tokens > most_expensive_tokens:
            most_expensive_tokens = tokens
            most_expensive_stage = stage
        stage_stats[stage] = {
            "calls": calls,
            "total_tokens": tokens,
            "success_rate": round((successes or 0) / calls, 3) if calls else 0.0,
            "avg_latency_ms": round(avg_lat or 0.0, 0),
        }
        if model:
            all_models[model] = all_models.get(model, 0) + (calls or 0)

    most_used_model = max(all_models, key=lambda m: all_models[m]) if all_models else "unknown"

    # Estimate total cost from all calls
    total_cost_usd = 0.0
    try:
        cost_rows = tracker._conn.execute(
            "SELECT model, SUM(prompt_tokens), SUM(completion_tokens) FROM llm_calls GROUP BY model"
        ).fetchall()
        for model, pt, ct in cost_rows:
            prices = tracker._lookup_prices(model or "")
            total_cost_usd += ((pt or 0) / 1000) * prices.get("input", 0.0)
            total_cost_usd += ((ct or 0) / 1000) * prices.get("output", 0.0)
    except Exception:
        pass

    # Distinct project count
    try:
        proj_count_row = tracker._conn.execute(
            "SELECT COUNT(DISTINCT project_id) FROM llm_calls WHERE project_id != 'default'"
        ).fetchone()
        total_projects = int(proj_count_row[0]) if proj_count_row else 0
    except Exception:
        total_projects = 0

    # Stage success rates from LearningLoop (more reliable than CostTracker for approval)
    ll = _get_learning_loop()
    stage_success_rates: dict[str, float] = {}
    if ll is not None:
        for stage in list(stage_stats.keys()):
            try:
                perf = ll.get_agent_performance(stage)
                if perf.total > 0:
                    stage_success_rates[stage] = round(perf.success_rate, 3)
            except Exception:
                pass

    return {
        "total_projects": total_projects,
        "total_llm_calls": total_calls,
        "total_tokens_used": total_tokens,
        "total_cost_usd": round(total_cost_usd, 4),
        "avg_tokens_per_project": round(total_tokens / total_projects, 0) if total_projects else 0,
        "avg_latency_ms": round(total_latency_ms / total_calls, 0) if total_calls else 0.0,
        "most_expensive_stage": most_expensive_stage,
        "most_used_model": most_used_model,
        "stage_stats": stage_stats,
        "stage_success_rates": stage_success_rates,
    }


# ---------------------------------------------------------------------------
# GET /analytics/projects/{id}
# ---------------------------------------------------------------------------

@router.get("/api/analytics/projects/{project_id}")
@router.get("/analytics/projects/{project_id}")
async def get_project_analytics(project_id: str) -> dict[str, Any]:
    """Per-project analytics: cost by stage, completion times, retry counts."""
    tracker = get_shared_cost_tracker()
    try:
        summary = tracker.get_project_summary(project_id)
    except Exception as exc:
        logger.warning("[analytics] project summary failed: project=%s error=%s", project_id, exc)
        return {"project_id": project_id, "error": str(exc), "stages": []}

    # Enrich with LearningLoop data per stage
    ll = _get_learning_loop()
    stages_out = []
    for stage_cost in summary.stages:
        stage_data: dict[str, Any] = {
            "stage": stage_cost.stage,
            "llm_calls": stage_cost.llm_calls,
            "total_tokens": stage_cost.total_tokens,
            "prompt_tokens": stage_cost.prompt_tokens,
            "completion_tokens": stage_cost.completion_tokens,
            "avg_latency_ms": round(stage_cost.avg_latency_ms, 0),
            "success_rate": round(stage_cost.success_rate, 3),
            "retries": stage_cost.retries,
        }
        if ll is not None:
            try:
                trajectories = ll.get_project_trajectories(project_id, stage=stage_cost.stage)
                stage_data["trajectory_count"] = len(trajectories)
                stage_data["approval_count"] = sum(1 for t in trajectories if t.get("approved"))
            except Exception:
                pass
        stages_out.append(stage_data)

    return {
        "project_id": project_id,
        "total_llm_calls": summary.total_llm_calls,
        "total_tokens": summary.total_tokens,
        "total_latency_seconds": summary.total_latency_seconds,
        "estimated_cost_usd": summary.estimated_cost_usd,
        "most_expensive_stage": summary.most_expensive_stage,
        "slowest_stage": summary.slowest_stage,
        "stages": stages_out,
    }


# ---------------------------------------------------------------------------
# GET /analytics/stage/{stage_name}
# ---------------------------------------------------------------------------

@router.get("/api/analytics/stage/{stage_name}")
@router.get("/analytics/stage/{stage_name}")
async def get_stage_analytics(stage_name: str) -> dict[str, Any]:
    """Per-stage performance analytics across all projects."""
    ll = _get_learning_loop()
    perf = None
    failure_patterns: list[str] = []

    if ll is not None:
        try:
            perf = ll.get_agent_performance(stage_name)
            failure_patterns = ll.get_failure_patterns(stage_name, limit=5)
        except Exception as exc:
            logger.warning("[analytics] stage perf failed: stage=%s error=%s", stage_name, exc)

    # Cost data from CostTracker
    tracker = get_shared_cost_tracker()
    try:
        cost = tracker.get_stage_cost(stage_name)
        avg_tokens = round(cost.total_tokens / cost.calls, 0) if cost.calls else 0
        avg_latency_ms = round(cost.total_latency_ms / cost.calls, 0) if cost.calls else 0
    except Exception:
        cost = None
        avg_tokens = 0
        avg_latency_ms = 0

    # P9-2a: include ModelRouter profile metadata so callers can confirm which
    # temperature / max_tokens profile is active for this stage.
    from ..llm.model_router import STAGE_PROFILES
    profile = STAGE_PROFILES.get(stage_name)
    model_profile: dict = {}
    if profile is not None:
        model_profile = {
            "provider": profile.provider,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
        }

    return {
        "stage": stage_name,
        "total_runs": perf.total if perf else (cost.calls if cost else 0),
        "approval_rate": round(perf.success_rate, 3) if perf else 0.0,
        "avg_retry_count": round(perf.avg_retries, 2) if perf else 0.0,
        "avg_tokens": avg_tokens or (round(perf.avg_tokens, 0) if perf else 0),
        "avg_latency_ms": avg_latency_ms or (round(perf.avg_latency, 0) if perf else 0),
        "common_failures": failure_patterns,
        "model_profile": model_profile,          # P9-2a: R9 exit criterion
    }


# ---------------------------------------------------------------------------
# GET /analytics/learning
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# GET /analytics/model-correlation   (P9-2a)
# ---------------------------------------------------------------------------

@router.get("/api/analytics/model-correlation")
@router.get("/analytics/model-correlation")
async def get_model_correlation(
    project_id: str = Query(default="", description="Filter to a single project (empty = all projects)"),
    stage: str = Query(default="", description="Filter to a single stage (empty = all stages)"),
) -> dict[str, Any]:
    """Approval-rate correlation by model profile (stage × temperature × model).

    Queries persisted LearningLoop trajectory data and annotates each group
    with the ModelRouter temperature/max_tokens profile for that stage.
    Results are grouped by (stage, agent_model) and sorted deterministically.

    This endpoint exposes only analytics metadata — no prompts, feedback text,
    API keys, or sensitive context are included in the response.

    Query parameters:
        project_id: When provided, restrict correlation to this project only.
        stage:      When provided, restrict correlation to this stage only.
    """
    ll = _get_learning_loop()
    if ll is None:
        return {
            "project_id": project_id or None,
            "stage": stage or None,
            "groups": [],
            "total_trajectories": 0,
        }

    try:
        groups = ll.get_trajectory_correlation(project_id=project_id, stage=stage)
    except Exception as exc:
        logger.warning("[analytics] model_correlation failed: %s", exc)
        groups = []

    total = sum(g["total"] for g in groups)
    return {
        "project_id": project_id or None,
        "stage": stage or None,
        "groups": groups,
        "total_trajectories": total,
    }


# ---------------------------------------------------------------------------
# GET /analytics/profiles   (P9-2a)
# ---------------------------------------------------------------------------

@router.get("/api/analytics/profiles")
@router.get("/analytics/profiles")
async def get_model_profiles() -> dict[str, Any]:
    """Return all ModelRouter stage profiles with validation status.

    Useful for confirming which temperature / max_tokens profile is active
    per stage and verifying that no profile violates documented constraints.
    """
    from ..llm.model_router import STAGE_PROFILES, validate_all_stage_profiles

    validation_errors = validate_all_stage_profiles()
    profiles_out = {}
    for stage_name, profile in sorted(STAGE_PROFILES.items()):
        profiles_out[stage_name] = {
            "provider": profile.provider,
            "model": profile.model,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
            "valid": stage_name not in validation_errors,
            "errors": validation_errors.get(stage_name, []),
        }

    return {
        "stage_count": len(STAGE_PROFILES),
        "invalid_count": len(validation_errors),
        "all_valid": len(validation_errors) == 0,
        "profiles": profiles_out,
    }


# ---------------------------------------------------------------------------
# GET /analytics/template-impact   (P9-2b)
# ---------------------------------------------------------------------------

@router.get("/api/analytics/template-impact")
@router.get("/analytics/template-impact")
async def get_template_impact(
    stage: str = Query(default="", description="Filter to a single stage (empty = all stages)"),
) -> dict[str, Any]:
    """Per-stage approval statistics split by whether a template was injected.

    Compares executions that received a TemplateEngine structural hint against
    those that did not.  Useful for measuring whether template injection
    improves reviewer approval rates without requiring dynamic tuning.

    Query parameters:
        stage: When provided, restrict results to this stage only.

    Response fields per stage entry:
        stage                      — stage name
        injected_count             — runs where a template was injected
        non_injected_count         — runs with no template injection
        injected_approved          — approved count for injected runs
        non_injected_approved      — approved count for non-injected runs
        injected_approval_rate     — float in [0.0, 1.0]
        non_injected_approval_rate — float in [0.0, 1.0]

    No prompts, reviewer feedback, or credentials are included in the response.
    """
    ll = _get_learning_loop()
    if ll is None:
        return {
            "stage_filter": stage or None,
            "stages": [],
            "total_injected": 0,
            "total_non_injected": 0,
        }

    try:
        entries = ll.get_template_impact(stage=stage or None)
    except Exception as exc:
        logger.warning("[analytics] template_impact failed: %s", exc)
        entries = []

    total_injected = sum(e["injected_count"] for e in entries)
    total_non_injected = sum(e["non_injected_count"] for e in entries)

    return {
        "stage_filter": stage or None,
        "stages": entries,
        "total_injected": total_injected,
        "total_non_injected": total_non_injected,
    }


@router.get("/api/analytics/learning")
@router.get("/analytics/learning")
async def get_learning_analytics() -> dict[str, Any]:
    """Aggregated lessons from LessonStore across all projects."""
    ls = _get_lesson_store()
    ll = _get_learning_loop()

    total_lessons = 0
    by_stage: dict[str, dict[str, Any]] = {}

    # Aggregate from LessonStore using known stages
    known_stages = [
        "Architect", "Designer", "Security", "BackendDeveloper", "FrontendDeveloper",
        "QA", "DevOps", "Document", "Retro", "Integration", "BugAnalyst",
        "ProductOwner", "StrategicReview", "SprintPlanning",
    ]

    if ls is not None:
        for stage in known_stages:
            try:
                lessons = ls.get_all_lessons(stage, limit=10)
                if lessons:
                    total_lessons += len(lessons)
                    top_failures = [
                        l.what_failed for l in lessons[:3] if l.what_failed
                    ]
                    by_stage[stage] = {
                        "lesson_count": len(lessons),
                        "top_failures": top_failures,
                    }
            except Exception:
                pass

    # Trajectory totals from LearningLoop
    total_trajectories = 0
    trajectory_by_stage: dict[str, dict] = {}
    if ll is not None:
        try:
            total_trajectories = ll.count_all_trajectories()
        except Exception:
            pass
        for stage in known_stages:
            try:
                perf = ll.get_agent_performance(stage)
                if perf.total > 0:
                    trajectory_by_stage[stage] = {
                        "total": perf.total,
                        "approval_rate": round(perf.success_rate, 3),
                        "avg_retries": round(perf.avg_retries, 2),
                    }
            except Exception:
                pass

    return {
        "total_lessons": total_lessons,
        "total_trajectories": total_trajectories,
        "by_stage": by_stage,
        "trajectory_by_stage": trajectory_by_stage,
    }

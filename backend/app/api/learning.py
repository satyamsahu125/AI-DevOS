from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api.dependencies import get_container
from ..kernel.container import Container

router = APIRouter(tags=["learning"])


@router.get("/learning/performance")
@router.get("/api/learning/performance")
def get_all_agent_performance(container: Container = Depends(get_container)):
    """Returns performance scores for all agents."""
    scorer = container.performance_scorer
    scores = scorer.score_all_agents()
    return {
        "scores": scores,
        "total_agents_with_data": len(scores),
        "agents_needing_attention": [
            s for s in scores if s.get("quality") == "needs_improvement"
        ],
    }


@router.get("/learning/performance/{stage}")
@router.get("/api/learning/performance/{stage}")
def get_stage_performance(
    stage: str, container: Container = Depends(get_container)
):
    """Performance score for one agent stage."""
    scorer = container.performance_scorer
    return scorer.score_agent(stage)


@router.get("/learning/insights/{stage}")
@router.get("/api/learning/insights/{stage}")
def get_stage_insights(
    stage: str, container: Container = Depends(get_container)
):
    """Lessons and patterns learned for a stage."""
    analyzer = container.prompt_analyzer
    return analyzer.analyze_stage(stage)


@router.get("/learning/patterns")
@router.get("/api/learning/patterns")
def search_patterns(
    query: str, container: Container = Depends(get_container)
):
    """Semantic search across past successful patterns."""
    analyzer = container.prompt_analyzer
    return {
        "query": query,
        "patterns": analyzer.get_cross_project_patterns(query=query, top_k=5),
    }

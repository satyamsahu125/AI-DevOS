from __future__ import annotations

from pydantic import BaseModel, Field


class ContributorSummary(BaseModel):
    """One contributor's per-sprint breakdown (inspired by gstack's /retro skill)."""

    name: str = ""
    commits: int = 0
    top_area: str = ""
    praise: str = ""
    growth_opportunity: str = ""


class SprintRetrospective(BaseModel):
    """Structured output of the Retro stage (inspired by gstack's /retro skill)."""

    window: str = ""
    total_commits: int = 0
    shipping_streak_days: int = 0
    contributors: list[ContributorSummary] = Field(default_factory=list)
    top_wins: list[str] = Field(default_factory=list)
    things_to_improve: list[str] = Field(default_factory=list)

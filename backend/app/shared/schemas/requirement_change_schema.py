from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class RequirementChange(BaseModel):
    change_id: str               # UUID
    project_id: str
    submitted_at: datetime
    description: str             # what the user wants to change
    change_type: str             # "add" | "remove" | "modify"
    affected_feature: str        # which feature is changing


class ImpactAnalysis(BaseModel):
    change_id: str
    project_id: str
    analyzed_at: datetime
    description: str             # what was requested
    affected_stages: list[str]   # stages that must re-run
    safe_stages: list[str]       # stages NOT affected
    affected_files: list[str]    # files that will be regenerated
    sprints_to_replan: list[int] # sprint numbers needing replan
    estimated_rerun_time: str    # "~3 stages"
    explanation: str             # plain English why these stages affected
    can_preserve: list[str]      # artifacts that can be kept as-is


class ChangeConfirmation(BaseModel):
    change_id: str
    confirmed: bool              # user confirmed the re-run
    user_comment: str | None = None     # optional extra context

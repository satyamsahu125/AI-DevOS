from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from ..prompt.scrum_master_builder import ScrumMasterPromptBuilder
from .base_action import LLMAction

logger = logging.getLogger(__name__)


class TaskItem(BaseModel):
    task_id: str
    title: str
    user_story_ref: str
    story_points: int
    assigned_agent: str
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    parallelizable: bool = True


class ScrumPlan(BaseModel):
    sprint_number: int = 1
    sprint_name: str = "Sprint 1"
    sprint_goal: str
    definition_of_done: list[str] = Field(default_factory=list)
    tasks: list[TaskItem] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    total_story_points: int = 0
    blocked_tasks: list[str] = Field(default_factory=list)
    parallelizable_tasks: list[list[str]] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    human_review_required: list[str] = Field(default_factory=list)
    anything_unclear: str = ""


class WriteScrumPlanAction(LLMAction):
    name = "WriteScrumPlan"
    description = "Transform a SprintPlan into an executable sprint ceremony structure and ScrumPlan."
    schema_model = ScrumPlan
    system_prompt = (
        "You are a Senior Scrum Master and Agile Coach. "
        "Respond with ONLY a single JSON object matching the ScrumPlan schema."
    )

    def __init__(self, prompt_builder: ScrumMasterPromptBuilder | None = None) -> None:
        super().__init__(prompt_builder or ScrumMasterPromptBuilder())

    def _parse_structured(self, content: str) -> dict[str, Any]:
        data = self.extract_json(content)
        parsed = ScrumPlan.model_validate(data)
        return parsed.model_dump(mode="json")

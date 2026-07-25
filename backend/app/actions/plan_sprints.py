from __future__ import annotations

from ..prompt.sprint_planner_builder import SprintPlannerPromptBuilder
from ..shared.schemas.sprint_schema import SprintPlanSchema
from .base_action import LLMAction


class PlanSprintsAction(LLMAction):
    """SprintPlannerAgent's action: produces a structured SprintPlanSchema."""

    name = "PlanSprints"
    description = "Break down requirements, architecture, and design into shippable agile sprints."
    schema_model = SprintPlanSchema
    system_prompt = (
        "You are a Senior Engineering Manager and Agile Coach. "
        "Respond with ONLY a single JSON object (no prose outside it) matching the SprintPlan schema: "
        "project_id (string), total_sprints (integer), rationale (string), "
        "sprints (list of Sprint objects with sprint_number, name, goal, features, tasks)."
    )

    def __init__(self, prompt_builder: SprintPlannerPromptBuilder | None = None) -> None:
        """Wire the SprintPlanner prompt builder this action uses."""
        super().__init__(prompt_builder or SprintPlannerPromptBuilder())

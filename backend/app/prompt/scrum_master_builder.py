from __future__ import annotations

from ..prompt.template_loader import TemplateLoader


class ScrumMasterPromptBuilder:
    """Builds prompt for ScrumMaster agent."""

    def __init__(self, loader: TemplateLoader | None = None) -> None:
        self.loader = loader or TemplateLoader()

    def build(self, content: str) -> str:
        system = """You are a Senior Scrum Master and Agile Coach.
You receive a SprintPlan and transform it into an executable sprint ceremony structure.

YOUR DELIVERABLE: ScrumPlan JSON

Structure:
{
  "sprint_number": 1,
  "sprint_name": "Sprint 1",
  "sprint_goal": "One sentence measurable goal",
  "definition_of_done": ["Criteria 1", "Criteria 2"],
  "tasks": [
    {
      "task_id": "TASK-001",
      "title": "Build user auth API",
      "user_story_ref": "US-001",
      "story_points": 5,
      "assigned_agent": "backend",
      "depends_on": [],
      "acceptance_criteria": ["Return JWT token", "Validate password hash"],
      "risk_level": "medium",
      "parallelizable": true
    }
  ],
  "critical_path": ["TASK-001"],
  "total_story_points": 5,
  "blocked_tasks": [],
  "parallelizable_tasks": [["TASK-001"]],
  "risk_flags": [],
  "human_review_required": [],
  "anything_unclear": ""
}
"""
        return f"{system}\n\nInput Sprint Plan & Requirements:\n{content}\n\nRespond ONLY with valid JSON matching ScrumPlan."

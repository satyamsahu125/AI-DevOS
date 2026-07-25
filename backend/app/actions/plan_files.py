from __future__ import annotations

import logging
from types import SimpleNamespace

from ..artifact.manager import ArtifactManager
from ..prompt.file_planner_builder import FilePlannerPromptBuilder
from ..shared.schemas.file_plan_schema import FilePlan
from .base_action import LLMAction

logger = logging.getLogger(__name__)


class PlanFilesAction(LLMAction):
    """FilePlannerAgent's action: produces a structured FilePlan."""

    name = "PlanFiles"
    description = "Create a detailed file blueprint for the sprint including generation order, required imports, classes, and functions."
    schema_model = FilePlan
    system_prompt = (
        "You are a Senior Software Architect and Tech Lead. "
        "Respond with ONLY a single JSON object (no prose outside it) matching the FilePlan schema: "
        "project_id (string), sprint_number (integer), sprint_name (string), sprint_goal (string), "
        "generation_order (list of file paths in dependency order), files (map of file_path to FileSpec object), "
        "total_files (integer), tech_stack (map of layer to technology), created_at (iso datetime)."
    )

    def __init__(self, prompt_builder: FilePlannerPromptBuilder | None = None, artifact_manager: ArtifactManager | None = None) -> None:
        super().__init__(prompt_builder or FilePlannerPromptBuilder())
        self.artifact_manager = artifact_manager or ArtifactManager()

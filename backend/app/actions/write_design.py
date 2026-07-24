from __future__ import annotations

from ..prompt.designer_builder import DesignerPromptBuilder
from ..shared.schemas.design_schema import DesignArtifact
from .base_action import LLMAction


class WriteDesignAction(LLMAction):
    """Designer's action: produces a structured DesignArtifact."""

    name = "WriteDesign"
    description = "Design the complete UI/UX spec: components, user flows, and design system."
    schema_model = DesignArtifact
    system_prompt = (
        "You are a Senior UI/UX Designer. Respond with ONLY a single JSON object (no prose outside it) "
        "with these keys: project_name (string), "
        "design_system (object with at least colors/fonts/spacing/breakpoints keys), "
        "user_flows (list of objects with name/steps/entry_point/success_end/error_end), "
        "components (list of objects with name/type/purpose/inputs/outputs/states -- "
        "states must include loading/error/empty for every component), "
        "page_layouts (list of objects mapping a page name to its component arrangement), "
        "api_dependencies (list of strings naming backend API endpoints each page needs), "
        "accessibility_notes (list of strings)."
    )

    def __init__(self, prompt_builder: DesignerPromptBuilder | None = None) -> None:
        """Wire the Designer prompt builder this action uses."""
        super().__init__(prompt_builder or DesignerPromptBuilder())

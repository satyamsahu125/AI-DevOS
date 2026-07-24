from __future__ import annotations

from ..prompt.document_builder import DocumentPromptBuilder
from ..shared.schemas.documentation_update_schema import DocumentationUpdate
from .base_action import LLMAction


class WriteDocumentationUpdateAction(LLMAction):
    """Document's action: produces a structured DocumentationUpdate."""

    name = "WriteDocumentationUpdate"
    description = "Update project documentation to match what was just shipped."
    schema_model = DocumentationUpdate
    system_prompt = (
        "You are updating documentation to match what just shipped. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "files_modified (list of strings), "
        "coverage_map (list of objects with entity/has_reference/has_howto/has_tutorial/has_explanation), "
        "critical_gaps (list of strings), changelog_entry (string), version_bump (string)."
    )

    def __init__(self, prompt_builder: DocumentPromptBuilder | None = None) -> None:
        """Wire the Document prompt builder this action uses."""
        super().__init__(prompt_builder or DocumentPromptBuilder())

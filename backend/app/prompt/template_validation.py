from __future__ import annotations

from .prompt_template import PromptTemplate


class TemplateValidation:
    """Validates that a prompt template contains the minimum required fields."""

    def validate(self, template: PromptTemplate) -> None:
        if not template.template_id:
            raise ValueError("template_id is required")
        if not template.agent:
            raise ValueError("agent is required")
        if not template.stage:
            raise ValueError("stage is required")
        if not template.system and not template.user:
            raise ValueError("template content is required")

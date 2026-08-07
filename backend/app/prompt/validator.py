from __future__ import annotations

from .template import PromptTemplate


class PromptValidator:
    """Validate prompt templates before they are used."""

    def validate(self, template: PromptTemplate) -> bool:
        return bool(template.name and template.system_template and template.user_template)

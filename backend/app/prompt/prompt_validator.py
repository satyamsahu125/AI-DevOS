from __future__ import annotations

import re
from typing import Any

from .prompt_template import PromptTemplate
from .prompt_variables import PromptVariables


class PromptValidationException(ValueError):
    """Raised when a prompt cannot be validated."""


class PromptValidator:
    """Validates that prompt templates, variable values, and prompt size are acceptable."""

    def __init__(self, max_tokens: int = 4000) -> None:
        self.max_tokens = max_tokens

    def validate(self, template: PromptTemplate, variables: PromptVariables, prompt_text: str) -> None:
        if not template.template_id:
            raise PromptValidationException("template_id is required")
        if not template.system and not template.user:
            raise PromptValidationException("prompt content is empty")
        if not prompt_text.strip():
            raise PromptValidationException("prompt text is empty")
        if self.estimate_tokens(prompt_text) > self.max_tokens:
            raise PromptValidationException("prompt exceeds max token size")

        missing = self._missing_variables(template, variables)
        if missing:
            raise PromptValidationException(f"missing variables: {', '.join(sorted(missing))}")

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def _missing_variables(self, template: PromptTemplate, variables: PromptVariables) -> list[str]:
        if variables is None:
            return self._extract_variables(template)

        placeholders = self._extract_variables(template)
        if not placeholders:
            return []

        values = variables.values if hasattr(variables, "values") else {}
        return [name for name in placeholders if name not in values]

    def _extract_variables(self, template: PromptTemplate) -> list[str]:
        content = "\n".join([template.system, template.user, template.rules])
        return sorted({match.group(1).strip() for match in re.finditer(r"\{\{(.*?)\}\}", content)})

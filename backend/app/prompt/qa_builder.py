from __future__ import annotations

from .builder import PromptBuilder


class QAPromptBuilder(PromptBuilder):
    """Prompt builder for QA generation."""

    def build(self, context: object | None = None) -> str:
        return f"QA prompt for {context}"

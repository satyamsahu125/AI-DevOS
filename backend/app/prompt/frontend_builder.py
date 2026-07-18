from __future__ import annotations

from .builder import PromptBuilder


class FrontendPromptBuilder(PromptBuilder):
    """Prompt builder for frontend generation."""

    def build(self, context: object | None = None) -> str:
        return f"Frontend prompt for {context}"

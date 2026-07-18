from __future__ import annotations

from .builder import PromptBuilder


class ArchitectPromptBuilder(PromptBuilder):
    """Prompt builder for architecture generation."""

    def build(self, context: object | None = None) -> str:
        return f"Architect prompt for {context}"

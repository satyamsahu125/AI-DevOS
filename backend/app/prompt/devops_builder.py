from __future__ import annotations

from .builder import PromptBuilder


class DevOpsPromptBuilder(PromptBuilder):
    """Prompt builder for DevOps generation."""

    def build(self, context: object | None = None) -> str:
        return f"DevOps prompt for {context}"

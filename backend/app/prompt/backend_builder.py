from __future__ import annotations

from .builder import PromptBuilder


class BackendPromptBuilder(PromptBuilder):
    """Prompt builder for backend generation."""

    def __init__(self) -> None:
        super().__init__(role="Backend Developer")

    def build(self, context: object | None = None) -> str:
        base = super().build(context)
        return f"Backend Prompt:\n{base}" if base else "Backend Prompt"

from __future__ import annotations

from .builder import PromptBuilder


class ProductOwnerPromptBuilder(PromptBuilder):
    """Prompt builder specialized for product-owner-style output."""

    def __init__(self) -> None:
        super().__init__(role="Product Owner")

    def build(self, context: object | None = None) -> str:
        base = super().build(context)
        return f"Product Owner Prompt:\n{base}" if base else "Product Owner Prompt"

from __future__ import annotations

from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent


class ProductOwnerAgent(BaseAgent):
    """Simple product-owner-style agent used by the documented workflow."""

    def __init__(self, prompt_builder: ProductOwnerPromptBuilder | None = None) -> None:
        self.prompt_builder = prompt_builder or ProductOwnerPromptBuilder()

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "") if context is not None else ""
        prompt = self.prompt_builder.build(content)
        return StageArtifact(
            artifact_id="",
            name="product-owner-output",
            content=prompt,
            status="Generated",
        )

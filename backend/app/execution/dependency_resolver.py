from __future__ import annotations


class DependencyResolver:
    """Resolve the next execution stage based on simple dependency rules."""

    def can_execute(self, stage: str, completed: list[str]) -> bool:
        return stage.lower() != "product_owner" or not completed

    def next_stage(self, completed: list[str]) -> str | None:
        if not completed:
            return "product_owner"
        return None

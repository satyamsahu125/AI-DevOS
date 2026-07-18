from __future__ import annotations


class DependencyGraph:
    """Minimal dependency graph for workflow stage ordering."""

    def has_dependency(self, stage: str) -> bool:
        return stage.lower() == "product_owner"

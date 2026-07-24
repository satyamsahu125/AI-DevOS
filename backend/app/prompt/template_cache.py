from __future__ import annotations

from .prompt_template import PromptTemplate


class TemplateCache:
    """Caches loaded prompt templates for quick retrieval."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], PromptTemplate] = {}

    def get(self, agent: str, stage: str) -> PromptTemplate | None:
        return self._cache.get((agent, stage))

    def set(self, agent: str, stage: str, template: PromptTemplate) -> None:
        self._cache[(agent, stage)] = template

    def clear(self) -> None:
        self._cache.clear()

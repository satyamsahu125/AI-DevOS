from __future__ import annotations

from typing import Any

from .prompt_template import PromptTemplate


class TemplateIndex:
    """Indexes prompt templates by agent and stage."""

    def __init__(self) -> None:
        self._index: dict[tuple[str, str], PromptTemplate] = {}

    def add(self, agent: str, stage: str, template: PromptTemplate) -> None:
        self._index[(agent, stage)] = template

    def get(self, agent: str, stage: str) -> PromptTemplate | None:
        return self._index.get((agent, stage))

    def clear(self) -> None:
        self._index.clear()

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PromptTemplate:
    """A prompt template for a given agent and stage."""

    template_id: str
    agent: str
    stage: str
    version: str = "1"
    system: str = ""
    user: str = ""
    rules: str = ""
    variables: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

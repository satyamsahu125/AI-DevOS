from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PromptPackage:
    """A fully assembled prompt payload for an LLM call."""

    package_id: str
    stage: str
    system_prompt: str = ""
    user_prompt: str = ""
    context_prompt: str = ""
    rules_prompt: str = ""
    memory_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

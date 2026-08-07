from __future__ import annotations

from typing import Any

from .context import AgentContext


class ContextValidator:
    """Validates context payloads before use."""

    def validate(self, context: AgentContext) -> None:
        if context.project_name == "" and context.requirements == "" and context.architecture == "":
            raise ValueError("context is empty")

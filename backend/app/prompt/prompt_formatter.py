from __future__ import annotations

from typing import Any


class PromptFormatter:
    """Formats prompt sections into a consistent presentation."""

    def format(self, *, system_prompt: str, user_prompt: str, context_prompt: str = "", rules_prompt: str = "", memory_prompt: str = "") -> dict[str, str]:
        return {
            "system_prompt": system_prompt.strip(),
            "user_prompt": user_prompt.strip(),
            "context_prompt": context_prompt.strip(),
            "rules_prompt": rules_prompt.strip(),
            "memory_prompt": memory_prompt.strip(),
        }

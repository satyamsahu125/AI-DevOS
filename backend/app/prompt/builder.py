from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PromptBuilder:
    """Simple prompt builder used by the documented orchestration flow."""

    sections: list[str] = field(default_factory=list)
    role: str = "General"

    def build(self, context: object | None = None) -> str:
        if context is None:
            context_text = "\n".join(self.sections)
        else:
            context_text = str(context)

        if not context_text:
            return f"{self.role} prompt"
        return f"{self.role} prompt\nContext: {context_text}"

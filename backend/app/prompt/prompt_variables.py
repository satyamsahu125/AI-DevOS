from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PromptVariables:
    """Values used to resolve prompt template variables."""

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any | None = None) -> Any:
        return self.values.get(name, default)

    def requires(self) -> list[str]:
        return sorted(self.values)

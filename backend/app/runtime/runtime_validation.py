from __future__ import annotations

from typing import Any


class RuntimeValidation:
    """Validates agent runtime dependencies and artifacts."""

    def validate(self, target: Any) -> None:
        if target is None:
            raise ValueError("target is required")

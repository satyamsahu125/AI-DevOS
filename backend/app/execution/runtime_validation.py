from __future__ import annotations

from ..shared.exceptions import ExecutionException


class RuntimeValidator:
    """Validates runtime execution payloads."""

    def validate(self, artifact: object) -> None:
        if artifact is None:
            raise ExecutionException("artifact is required")

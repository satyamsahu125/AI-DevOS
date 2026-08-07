from __future__ import annotations

from ..shared.exceptions import DependencyException


class AgentValidation:
    """Validates agent registrations."""

    @staticmethod
    def validate_name(name: str) -> None:
        if not name or not str(name).strip():
            raise DependencyException("agent name is required")

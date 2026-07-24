from __future__ import annotations

from ..shared.exceptions import DependencyException


class DependencyValidation:
    """Validates dependency descriptors."""

    @staticmethod
    def validate_name(name: str) -> None:
        if not name or not str(name).strip():
            raise DependencyException("dependency name is required")

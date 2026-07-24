from __future__ import annotations

from ..shared.exceptions import DependencyException


class RegistryValidation:
    """Validates service registry descriptors."""

    @staticmethod
    def validate_name(name: str) -> None:
        if not name or not str(name).strip():
            raise DependencyException("service name is required")

    @staticmethod
    def validate_descriptor(descriptor: object) -> None:
        if descriptor is None:
            raise DependencyException("service descriptor is required")

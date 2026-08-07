from __future__ import annotations

from ...shared.exceptions import DependencyException


class ProviderValidationException(DependencyException):
    """Raised when a provider cannot validate a request."""


class ProviderValidation:
    """Validation helpers for provider implementations."""

    @staticmethod
    def validate_request(request: object) -> None:
        if request is None:
            raise ProviderValidationException("request is required")
        if not getattr(request, "provider", None):
            raise ProviderValidationException("provider is required")
        if not getattr(request, "model", None):
            raise ProviderValidationException("model is required")

    @staticmethod
    def validate_response(response: object) -> None:
        if response is None:
            raise ProviderValidationException("response is required")

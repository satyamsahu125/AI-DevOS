from app.shared.exceptions.base import ApplicationException


class DependencyException(ApplicationException):
    """Raised when a dependency or execution order is invalid."""

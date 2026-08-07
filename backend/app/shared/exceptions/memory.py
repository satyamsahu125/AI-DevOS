from app.shared.exceptions.base import ApplicationException


class MemoryException(ApplicationException):
    """Raised when memory store operations fail."""

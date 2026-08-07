from app.shared.exceptions.base import ApplicationException


class SessionException(ApplicationException):
    """Raised when a session lifecycle operation fails."""

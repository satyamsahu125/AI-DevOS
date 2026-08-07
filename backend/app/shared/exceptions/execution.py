from app.shared.exceptions.base import ApplicationException


class ExecutionException(ApplicationException):
    """Raised when execution fails or is interrupted."""

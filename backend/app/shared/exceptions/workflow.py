from app.shared.exceptions.base import ApplicationException


class WorkflowException(ApplicationException):
    """Raised when workflow state or transitions are invalid."""

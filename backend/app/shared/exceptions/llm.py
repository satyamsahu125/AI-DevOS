from app.shared.exceptions.base import ApplicationException


class LLMException(ApplicationException):
    """Raised when LLM requests or responses fail."""

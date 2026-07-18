from app.shared.exceptions.base import ApplicationException


class ConfigurationException(ApplicationException):
    """Raised when configuration is missing or invalid."""

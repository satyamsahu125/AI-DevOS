from app.shared.exceptions.base import ApplicationException


class ArtifactException(ApplicationException):
    """Raised when artifact storage or retrieval fails."""

class ApplicationException(Exception):
    """Base exception for all application-level failures."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

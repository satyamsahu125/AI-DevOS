class ConfigurationException(Exception):
    """Raised when required configuration is missing or invalid."""


class DependencyException(Exception):
    """Raised when a dependency relationship is invalid."""

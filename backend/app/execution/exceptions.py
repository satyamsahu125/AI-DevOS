from __future__ import annotations


class ExecutionException(Exception):
    """Base exception for execution package failures."""


class AgentResolutionException(ExecutionException):
    """Raised when the correct agent cannot be resolved for a stage."""


class SchemaValidationError(ExecutionException):
    """Raised when LLM output cannot be parsed into the expected structured schema."""

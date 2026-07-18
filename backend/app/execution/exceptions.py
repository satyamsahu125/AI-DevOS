from __future__ import annotations


class ExecutionException(Exception):
    """Base exception for execution package failures."""


class AgentResolutionException(ExecutionException):
    """Raised when the correct agent cannot be resolved for a stage."""

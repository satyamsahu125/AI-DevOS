"""Workflow middleware package.

Each middleware handles exactly one cross-cutting concern that fires
around a stage execution (trajectory recording, checkpoint save/delete,
git commits, etc.). WorkflowEngine composes them via the StageRunner
``on_attempt`` hook and its own post-approval sequence.
"""
from .checkpoint import CheckpointMiddleware
from .git import GitMiddleware
from .learning import LearningMiddleware

__all__ = ["CheckpointMiddleware", "GitMiddleware", "LearningMiddleware"]

from __future__ import annotations

from ..review.reviewer import ReviewResult
from ..shared.exceptions import WorkflowException
from ..shared.models.workflow import Workflow


class WorkflowRuntimeValidator:
    """Validates workflow runtime state and review outcomes."""

    def validate(self, workflow: Workflow, review: ReviewResult) -> None:
        if workflow.current_stage is None:
            raise WorkflowException("workflow stage is required")
        if not review.approved and not review.overall_feedback:
            raise WorkflowException("review feedback is required")

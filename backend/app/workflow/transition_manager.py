from __future__ import annotations

from ..shared.enums.workflow_state import WorkflowState


class TransitionManager:
    """Transitions workflow state through the documented lifecycle."""

    def next_state(self, current_state: WorkflowState, approved: bool) -> WorkflowState:
        if approved:
            return WorkflowState.Completed
        return WorkflowState.WaitingForReview

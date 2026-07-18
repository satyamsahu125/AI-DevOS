from __future__ import annotations

from ..shared.enums.workflow_state import WorkflowState


class WorkflowTransition:
    """Small transition helper for the documented workflow lifecycle."""

    def transition(self, state: WorkflowState) -> WorkflowState:
        return state

from __future__ import annotations

from dataclasses import dataclass

from ..shared.enums.workflow_state import WorkflowState


@dataclass(slots=True)
class RuntimeState:
    """Small state object for workflow runtime progress."""

    state: WorkflowState = WorkflowState.Created

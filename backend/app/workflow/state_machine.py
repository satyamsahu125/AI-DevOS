from __future__ import annotations

from ..shared.enums.workflow_state import WorkflowState


class WorkflowStateMachine:
    def __init__(self) -> None:
        self.state = WorkflowState.Created

    def start(self) -> None:
        self.state = WorkflowState.Running

    def approve(self) -> None:
        self.state = WorkflowState.Approved

    def complete(self) -> None:
        self.state = WorkflowState.Completed

from __future__ import annotations

import logging

from ..shared.enums.workflow_state import WorkflowState

logger = logging.getLogger(__name__)


class WorkflowStateMachine:
    """Tracks the current WorkflowState for one workflow run.

    Owned exclusively by WorkflowEngine; no other component may mutate
    workflow state directly.
    """

    def __init__(self) -> None:
        """Initialize the state machine in the Created state."""
        self.state = WorkflowState.Created

    def start(self) -> None:
        """Transition to Running when stage execution begins."""
        self.state = WorkflowState.Running
        logger.debug("workflow state -> Running")

    def approve(self) -> None:
        """Transition to Approved after the Reviewer approves the stage artifact."""
        self.state = WorkflowState.Approved
        logger.debug("workflow state -> Approved")

    def complete(self) -> None:
        """Transition to Completed once the workflow has no remaining stages."""
        self.state = WorkflowState.Completed
        logger.debug("workflow state -> Completed")

    def fail(self) -> None:
        """Transition to Failed once RetryPolicy exhausts all retry attempts."""
        self.state = WorkflowState.Failed
        logger.debug("workflow state -> Failed")

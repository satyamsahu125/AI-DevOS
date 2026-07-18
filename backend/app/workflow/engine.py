from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..execution.manager import ExecutionManager
from ..review.manager import ReviewManager
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.stage import Stage
from ..shared.enums.workflow_state import WorkflowState
from ..shared.models.workflow import Workflow
from .dependency import WorkflowDependency
from .state_machine import WorkflowStateMachine
from .transition import WorkflowTransition


class WorkflowEngine:
    def __init__(self) -> None:
        self.dependency = WorkflowDependency("ProductOwner")
        self.state_machine = WorkflowStateMachine()
        self.execution_manager = ExecutionManager(ArtifactManager())
        self.review_manager = ReviewManager()
        self.transition = WorkflowTransition()

    def run(self, stage_name: str, content: str) -> WorkflowResult:
        self.state_machine.start()
        execution_result = self.execution_manager.execute_stage(stage_name, content)
        artifact = execution_result.artifact
        review_result = self.review_manager.review(artifact)
        workflow = Workflow(
            id="",
            project_id="",
            current_stage=Stage(stage_name),
            state=WorkflowState.Created,
        )
        if review_result.approved:
            workflow.state = self.transition.transition(WorkflowState.Approved)
            self.state_machine.approve()
            self.state_machine.complete()
            return WorkflowResult(workflow=workflow, success=True, message="workflow completed")
        workflow.state = self.transition.transition(WorkflowState.Running)
        return WorkflowResult(workflow=workflow, success=False, message=review_result.feedback)

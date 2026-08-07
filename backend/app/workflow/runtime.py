from __future__ import annotations

from ..execution.agent_runtime import AgentRuntime
from ..review.reviewer import Reviewer
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.stage import Stage
from ..shared.enums.workflow_state import WorkflowState
from ..shared.models.workflow import Workflow
from .runtime_state import RuntimeState
from .transition_manager import TransitionManager
from .runtime_validation import WorkflowRuntimeValidator


class WorkflowRuntime:
    """Coordinates a full workflow lifecycle for the documented runtime."""

    def __init__(self, agent_runtime: AgentRuntime | None = None, reviewer: Reviewer | None = None, transition_manager: TransitionManager | None = None, validator: WorkflowRuntimeValidator | None = None) -> None:
        self.agent_runtime = agent_runtime or AgentRuntime()
        self.reviewer = reviewer or Reviewer()
        self.transition_manager = transition_manager or TransitionManager()
        self.validator = validator or WorkflowRuntimeValidator()

    def run(self, stage_name: str, content: str) -> WorkflowResult:
        result = self.agent_runtime.execute(stage_name, content)
        review = self.reviewer.review(result.artifact)
        workflow = Workflow(
            id="workflow-1",
            project_id="project-1",
            current_stage=Stage(stage_name),
            state=WorkflowState.Completed if review.approved else WorkflowState.WaitingForReview,
        )
        self.validator.validate(workflow, review)
        return WorkflowResult(workflow=workflow, success=review.approved, message=review.overall_feedback)

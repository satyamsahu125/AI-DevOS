from dataclasses import dataclass

from ..models.workflow import Workflow


@dataclass(slots=True)
class WorkflowResult:
    workflow: Workflow
    success: bool
    message: str
    stopped: bool = False

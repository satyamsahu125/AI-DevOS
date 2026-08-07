from dataclasses import dataclass


@dataclass(slots=True)
class WorkflowRequest:
    project_id: str
    request: str = ""

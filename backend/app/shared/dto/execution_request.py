from dataclasses import dataclass

from ..enums.stage import Stage


@dataclass(slots=True)
class ExecutionRequest:
    project_id: str
    stage: Stage
    task: str

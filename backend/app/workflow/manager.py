from __future__ import annotations

from ..shared.dto.workflow_result import WorkflowResult
from .engine import WorkflowEngine


class WorkflowManager:
    def __init__(self) -> None:
        self.engine = WorkflowEngine()

    def run_stage(self, stage_name: str, content: str) -> WorkflowResult:
        return self.engine.run(stage_name, content)

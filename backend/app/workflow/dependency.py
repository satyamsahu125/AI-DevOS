from __future__ import annotations

from typing import List


class WorkflowDependency:
    def __init__(self, stage_name: str, prerequisites: List[str] | None = None) -> None:
        self.stage_name = stage_name
        self.prerequisites = prerequisites or []

    def validate(self) -> bool:
        return True

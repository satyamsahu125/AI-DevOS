from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutionPlan:
    workflow_id: str
    stages: list[str]
    current_stage: str
    completed_stages: list[str]
    failed_stages: list[str]
    metadata: dict = field(default_factory=dict)

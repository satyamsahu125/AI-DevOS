from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutionMetrics:
    executed_stages: int = 0
    failed_stages: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

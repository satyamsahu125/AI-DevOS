from __future__ import annotations

from .execution_plan import ExecutionPlan


class ExecutionScheduler:
    """Schedule the next stage from an execution plan."""

    def schedule(self, plan: ExecutionPlan) -> str:
        return plan.current_stage or plan.stages[0] if plan.stages else ""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateResult:
    """Result returned by a gate endpoint (approve / revise / adjust).

    Produced by the gates API router (api/gates.py) and consumed by the
    frontend to decide what to show after the user acts on a gate.

    status values:
      "resumed"           — gate approved, pipeline is running again
      "revision_requested"— stage will be re-run with injected feedback
      "adjusted"          — sprint plan re-running with constraints applied
      "error"             — gate action failed; see message for details
    """

    status: str                        # "resumed" | "revision_requested" | "adjusted" | "error"
    project_id: str = ""
    gate: str = ""                     # "architecture" | "design" | "sprint_plan"
    next_state: str = ""               # ProjectState.value after this action
    next_stage: str = ""               # stage that will run next (for "resumed")
    message: str = ""
    artifact: dict[str, Any] = field(default_factory=dict)  # current gate artifact (for GET /gates/current)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "project_id": self.project_id,
            "gate": self.gate,
            "next_state": self.next_state,
            "next_stage": self.next_stage,
            "message": self.message,
        }

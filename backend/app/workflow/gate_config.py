"""Declarative review gate configuration loader.

Loads gates.yaml and provides typed access to per-stage review gate configuration.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


GATES_PATH = Path(__file__).parent / "gates.yaml"


@dataclass
class StageGateConfig:
    """Configuration for a single stage's review gate."""
    review_type: str                    # "human" | "ai" | "both"
    ai_reviewer: Optional[str] = None
    ai_threshold: float = 0.85
    timeout_hours: int = 24
    escalation: Optional[str] = None
    human_escalation_threshold: Optional[float] = None


class GateConfigLoader:
    """Loads and provides access to gate configuration from gates.yaml."""

    def __init__(self, path: Path = GATES_PATH) -> None:
        with open(path) as f:
            raw = yaml.safe_load(f)
        self._defaults = raw.get("defaults", {})
        self._stages = raw.get("stages", {})

    def get(self, stage_name: str) -> StageGateConfig:
        """Get gate configuration for a stage, merging with defaults."""
        data = {**self._defaults, **self._stages.get(stage_name, {})}
        return StageGateConfig(
            review_type=data.get("review_type", "ai"),
            ai_reviewer=data.get("ai_reviewer"),
            ai_threshold=float(data.get("ai_threshold", 0.85)),
            timeout_hours=int(data.get("timeout_hours", 24)),
            escalation=data.get("escalation"),
            human_escalation_threshold=data.get("human_escalation_threshold"),
        )


# Import yaml here to avoid circular import issues
import yaml
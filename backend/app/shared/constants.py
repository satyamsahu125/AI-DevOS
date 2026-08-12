"""Shared constants for the AI DevOS workflow layer.

Centralising these prevents the silent-mismatch bugs that occur when
the same magic string is defined independently in multiple modules.
Import from here; never redeclare these values elsewhere.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Memory keys
# ---------------------------------------------------------------------------

# Durable slot holding the approved DesignArtifact.  Survives any number of
# intervening stages (unlike the single-slot predecessor message).
# FrontendDeveloper, QA, and FileStructurePlanner all read from this slot.
DESIGN_MEMORY_KEY: str = "design:latest"

# Single-slot inbox for the most-recently-approved stage's AgentMessage.
# Each stage approval overwrites it; the next stage reads it as "predecessor output".
WORKFLOW_MESSAGE_KEY: str = "workflow:latest_message"

# ---------------------------------------------------------------------------
# Stage groupings
# ---------------------------------------------------------------------------

# Stages that must always receive the approved design spec in their context,
# regardless of how many stages ran between Designer and them.
DESIGN_DEPENDENT_STAGES: frozenset[str] = frozenset({
    "FrontendDeveloper",
    "QA",
    "FileStructurePlanner",
})

# Stages that trigger a human-review gate pause after they complete.
# Maps stage key (as used in DependencyGraph.STAGE_ORDER) → gate name.
GATE_STAGES: dict[str, str] = {
    "architect":     "architecture",
    "designer":      "design",
    "sprint_planner": "sprint_plan",
}

# Stages whose gate feedback is stored in memory and injected on the next run.
GATE_FEEDBACK_MAP: dict[str, str] = {
    "Architect":      "architecture",
    "Designer":       "design",
    "SprintPlanning": "sprint_plan",
}

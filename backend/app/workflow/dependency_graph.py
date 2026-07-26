from __future__ import annotations

from ..shared.enums.stage import Stage
from .stage_lookup import resolve_stage_name


class DependencyGraph:
    """Minimal dependency graph for workflow stage ordering.

    STAGE_ORDER is the canonical pipeline sequence (registry keys, matching
    AgentFactory's registrations). STAGE_DEPENDENCIES expresses the same
    ordering as an explicit dependency map keyed by Stage: Designer depends
    on Architect; FrontendDeveloper depends on both Security and Designer,
    so no frontend code is ever produced without an approved design spec.
    """

    STAGE_ORDER: list[str] = [
        "strategic_review",
        "product_owner",
        "architect",
        "designer",
        "security",
        "sprint_planner",
        "scrum_master",
        "file_planner",
        "backend",
        "frontend",
        "qa",
        "devops",
        "document",
        "retro",
    ]

    STAGE_DEPENDENCIES: dict[Stage, list[Stage]] = {
        Stage.StrategicReview: [],
        Stage.ProductOwner: [Stage.StrategicReview],
        Stage.Architect: [Stage.ProductOwner],
        Stage.Designer: [Stage.Architect],
        Stage.Security: [Stage.Designer],
        Stage.SprintPlanning: [Stage.Security],
        Stage.ScrumMaster: [Stage.SprintPlanning],
        Stage.FileStructurePlanner: [Stage.ScrumMaster],
        Stage.BackendDeveloper: [Stage.Security, Stage.FileStructurePlanner, Stage.SprintPlanning],
        Stage.FrontendDeveloper: [Stage.Security, Stage.Designer, Stage.FileStructurePlanner, Stage.SprintPlanning],
        Stage.QA: [Stage.BackendDeveloper, Stage.FrontendDeveloper],
        Stage.DevOps: [Stage.QA],
        Stage.Document: [Stage.DevOps],
        Stage.Retro: [Stage.Document],
    }

    def has_dependency(self, stage: str) -> bool:
        """Return True if stage has at least one prerequisite in STAGE_DEPENDENCIES.

        Resolves the registry key string (e.g. ``"product_owner"``) to a Stage
        enum via resolve_stage_name, then looks it up in STAGE_DEPENDENCIES.
        The old implementation hardcoded ``stage == "product_owner"``, which made
        every stage except ProductOwner look dependency-free — meaning the graph
        was never consulted for any other stage.
        """
        try:
            resolved = resolve_stage_name(stage)
            stage_enum = Stage(resolved)
            return bool(self.STAGE_DEPENDENCIES.get(stage_enum))
        except Exception:
            # resolve_stage_name raises ApplicationException for unknown keys;
            # Stage() raises ValueError for unknown enum values. Either way —
            # if we can't resolve it, it has no known dependency.
            return False

    @classmethod
    def ordered_stages(cls) -> list[Stage]:
        """Return STAGE_ORDER's registry keys resolved to their canonical Stage enum members, in pipeline order."""
        return [Stage(resolve_stage_name(key)) for key in cls.STAGE_ORDER]

    @classmethod
    def get_next_stage(cls, current_stage: Stage) -> Stage | None:
        """Return the stage immediately after current_stage in STAGE_ORDER, or None if it's the last stage."""
        ordered = cls.ordered_stages()
        try:
            index = ordered.index(current_stage)
        except ValueError:
            return None
        if index + 1 >= len(ordered):
            return None
        return ordered[index + 1]

    @classmethod
    def get_stage_dependencies(cls, stage: Stage) -> list[Stage]:
        """Return the stages that must complete before stage can run."""
        return cls.STAGE_DEPENDENCIES.get(stage, [])

from __future__ import annotations

import json
from pathlib import Path
from ..shared.enums.stage import Stage
from .stage_lookup import resolve_stage_name


class DependencyGraph:
    """Minimal dependency graph for workflow stage ordering.

    STAGE_ORDER lists only the top-level Discovery and Release stages.
    Sprint-internal stages (ScrumMaster, FileStructurePlanner, Backend,
    Frontend, TechLead, BugAnalyst, SprintDeploy, SprintReview) are managed
    by SprintSupervisor via SprintGraph and do not appear here.

    STAGE_DEPENDENCIES expresses ordering as an explicit dependency map keyed
    by Stage: Designer depends on Architect; FrontendDeveloper depends on both
    Security and Designer, so no frontend code is ever produced without an
    approved design spec.
    """

    # Loaded dynamically from workflow.json
    STAGE_ORDER: list[str] = []
    STAGE_DEPENDENCIES: dict[Stage, list[Stage]] = {}

    @classmethod
    def _load_config(cls) -> None:
        """Load stage definitions from workflow.json."""
        if cls.STAGE_ORDER:
            return
        
        config_path = Path(__file__).parent / "workflow.json"
        if not config_path.exists():
            return
            
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for stage in data.get("stages", []):
                name = stage["name"]
                cls.STAGE_ORDER.append(name)
                
                try:
                    stage_enum = Stage(resolve_stage_name(name))
                    deps = []
                    for req in stage.get("requires", []):
                        # Convert requirement names to Stage if they match
                        for r_stage in data.get("stages", []):
                            if req in r_stage.get("emits", []):
                                deps.append(Stage(resolve_stage_name(r_stage["name"])))
                    cls.STAGE_DEPENDENCIES[stage_enum] = deps
                except Exception:
                    continue
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to load workflow.json: %s", e)

    def has_dependency(self, stage: str) -> bool:
        """Return True if stage has at least one prerequisite in STAGE_DEPENDENCIES.

        Resolves the registry key string (e.g. ``"product_owner"``) to a Stage
        enum via resolve_stage_name, then looks it up in STAGE_DEPENDENCIES.
        The old implementation hardcoded ``stage == "product_owner"``, which made
        every stage except ProductOwner look dependency-free — meaning the graph
        was never consulted for any other stage.
        """
        self.__class__._load_config()
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
        cls._load_config()
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
        cls._load_config()
        return cls.STAGE_DEPENDENCIES.get(stage, [])

DependencyGraph._load_config()

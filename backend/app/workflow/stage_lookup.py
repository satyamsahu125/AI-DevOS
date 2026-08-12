from __future__ import annotations

from ..shared.enums.stage import Stage
from ..shared.exceptions import ApplicationException

_REGISTRY_KEY_TO_STAGE: dict[str, Stage] = {
    "product_owner": Stage.ProductOwner,
    "architect": Stage.Architect,
    "designer": Stage.Designer,
    "security": Stage.Security,
    "file_planner": Stage.FileStructurePlanner,
    "backend": Stage.BackendDeveloper,
    "frontend": Stage.FrontendDeveloper,
    "qa": Stage.QA,
    "document": Stage.Document,
    "devops": Stage.DevOps,
    "retro": Stage.Retro,
    "strategic_review": Stage.StrategicReview,
    "reviewer": Stage.Reviewer,
    "planner": Stage.FileStructurePlanner,
    "sprint_planner": Stage.SprintPlanning,
    "sprintplanner": Stage.SprintPlanning,
    "sprint_planning": Stage.SprintPlanning,
    "sprintplanning": Stage.SprintPlanning,
    "scrum_master": Stage.ScrumMaster,
    "scrummaster": Stage.ScrumMaster,
    "clarification": Stage.Clarification,
    "tech_lead": Stage.TechLead,
    "bug_analyst": Stage.BugAnalyst,
    "sprint_deploy": Stage.SprintDeploy,
    "sprint_review": Stage.SprintReview,
    # R6: Integration Developer
    "integration": Stage.Integration,
    "integration_developer": Stage.Integration,
    "integrationdeveloper": Stage.Integration,
    # SprintDeltaPlanner
    "sprint_delta": Stage.SprintDelta,
    "sprintdelta": Stage.SprintDelta,
    "sprint_delta_planner": Stage.SprintDelta,
}


def resolve_stage_name(stage_name: str) -> str:
    """Resolve stage_name to the Stage enum's canonical PascalCase value.

    Accepts either the Stage enum's own value ("ProductOwner") or the
    AgentFactory registry key form ("product_owner") -- so callers (API
    clients, debug scripts) don't have to know which casing WorkflowEngine
    expects internally.
    """
    try:
        return Stage(stage_name).value
    except ValueError:
        pass
    normalized = stage_name.strip().lower().replace(" ", "_").replace("-", "_")
    stage = _REGISTRY_KEY_TO_STAGE.get(normalized)
    if stage is None:
        raise ApplicationException(f"unknown stage: {stage_name}")
    return stage.value

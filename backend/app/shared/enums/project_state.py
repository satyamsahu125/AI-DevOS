from enum import Enum


class ProjectState(str, Enum):
    """
    Every project moves through these states in order.
    State persists to project.json on every transition.
    If process crashes, resume from last saved state.
    """
    EMPTY                   = "empty"
    CLARIFYING              = "clarifying"         # Q&A agent running
    REQUIREMENTS_READY      = "requirements_ready"
    ARCHITECTURE_READY      = "architecture_ready"
    DESIGN_READY            = "design_ready"
    DESIGN_REVIEW_PENDING   = "design_review_pending"  # waiting for user
    DESIGN_APPROVED         = "design_approved"
    SPRINT_PLAN_READY       = "sprint_plan_ready"
    SPRINT_IN_PROGRESS      = "sprint_in_progress"  # has sub-state
    SPRINT_COMPLETE         = "sprint_complete"
    ALL_SPRINTS_COMPLETE    = "all_sprints_complete"
    QA_COMPLETE             = "qa_complete"
    DEPLOYABLE              = "deployable"
    DONE                    = "done"
    FAILED                  = "failed"
    PAUSED                  = "paused"

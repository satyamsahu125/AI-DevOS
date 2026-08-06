from enum import Enum


class ProjectState(str, Enum):
    """
    Every project moves through these states in order.
    State persists to project.json on every transition.
    If process crashes, resume from last saved state.
    """
    EMPTY                   = "empty"
    CLARIFYING              = "clarifying"         # Q&A agent running Phase A
    QA_PENDING              = "qa_pending"         # Pipeline paused — questions generated, waiting for answers
    QA_IN_PROGRESS          = "qa_in_progress"     # User is actively answering questions
    QA_COMPLETE             = "qa_complete"        # All questions answered — pipeline can continue
    REQUIREMENTS_READY      = "requirements_ready"
    ARCHITECTURE_READY      = "architecture_ready"
    DESIGN_READY            = "design_ready"
    ARCHITECTURE_REVIEW_PENDING = "architecture_review_pending"  # waiting for human gate
    DESIGN_REVIEW_PENDING   = "design_review_pending"            # waiting for human gate
    SPRINT_PLAN_REVIEW_PENDING = "sprint_plan_review_pending"    # waiting for human gate
    DESIGN_APPROVED         = "design_approved"
    SPRINT_PLAN_READY       = "sprint_plan_ready"
    SPRINT_IN_PROGRESS      = "sprint_in_progress"  # has sub-state
    SPRINT_COMPLETE         = "sprint_complete"
    SPRINT_BLOCKED          = "sprint_blocked"      # retry limits exceeded, human intervention required
    ALL_SPRINTS_COMPLETE    = "all_sprints_complete"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    CHANGE_REQUESTED     = "change_requested"
    IMPACT_ANALYZED      = "impact_analyzed"
    REPLANNING           = "replanning"
    RESUMING_FROM_CHANGE = "resuming_from_change"
    DEPLOYABLE              = "deployable"
    DONE                    = "done"
    FAILED                  = "failed"
    PAUSED                  = "paused"


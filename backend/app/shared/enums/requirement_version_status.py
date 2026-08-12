from enum import Enum


class RequirementVersionStatus(str, Enum):
    """Lifecycle state of a single RequirementVersion record.

    CURRENT     — the version that defines the project's active requirements.
                  Exactly one CURRENT version must exist per project at any time.
    SUPERSEDED  — a prior version that has been replaced by a newer CURRENT version.
    PROPOSED    — a candidate change that has been submitted but not yet accepted.
    REJECTED    — a change that was reviewed and explicitly declined.
    """
    CURRENT    = "current"
    SUPERSEDED = "superseded"
    PROPOSED   = "proposed"
    REJECTED   = "rejected"

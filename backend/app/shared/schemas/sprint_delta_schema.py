from __future__ import annotations

from pydantic import BaseModel, Field


class FileOperationDecision(BaseModel):
    """The decided operation for one file in a sprint."""

    path: str = ""
    operation: str = "create"           # "create" | "update" | "patch"
    rationale: str = ""                 # why this operation was chosen
    change_description: str = ""        # specific change instructions (for update/patch)
    responsible_stage: str = "backend"  # backend | frontend | devops


class SprintDeltaArtifact(BaseModel):
    """Produced by SprintDeltaPlanner — explicit per-file operation decisions for one sprint.

    Consumed by WriteFilePlanAction to set operation/change_description reliably
    instead of relying on the FilePlan LLM to infer them from a file list.
    """

    sprint_number: int = 1
    sprint_goal: str = ""
    new_modules: list[str] = Field(default_factory=list)
    updated_modules: list[str] = Field(default_factory=list)
    decisions: list[FileOperationDecision] = Field(default_factory=list)

    def get_decision(self, path: str) -> FileOperationDecision | None:
        """Look up the decision for a specific file path."""
        for d in self.decisions:
            if d.path == path:
                return d
        return None

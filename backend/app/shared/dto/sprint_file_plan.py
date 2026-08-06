from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SprintFileEntry:
    """Describes how one file should be handled in a sprint.

    Replaces the LLM blindly outputting a list of files to create with a
    typed plan that explicitly carries the operation — so Sprint 2 and beyond
    correctly update existing files instead of overwriting them with blanks
    or duplicating logic from Sprint 1.
    """

    path: str
    operation: Literal["create", "update", "patch"] = "create"
    responsible_stage: str = ""    # "backend" | "frontend"
    purpose: str = ""              # brief description for the LLM
    change_description: str = ""   # for "update"/"patch": what specifically to change


@dataclass
class SprintFilePlan:
    """Complete file plan for one sprint, including existing-file operations.

    Produced by FileStructurePlanner and consumed by WriteProjectFilesAction.
    Unlike FilePlan (which is flat), SprintFilePlan carries sprint number and
    a discriminated list of operations so Agile update semantics are explicit.

    Design principle: all "update" and "patch" files have a non-empty
    change_description so the LLM knows what to add/change — not just "update
    this file" (which would produce unchanged output).
    """

    project_id: str
    sprint_number: int
    sprint_goal: str = ""
    files: list[SprintFileEntry] = field(default_factory=list)

    @property
    def creates(self) -> list[SprintFileEntry]:
        return [f for f in self.files if f.operation == "create"]

    @property
    def updates(self) -> list[SprintFileEntry]:
        return [f for f in self.files if f.operation == "update"]

    @property
    def patches(self) -> list[SprintFileEntry]:
        return [f for f in self.files if f.operation == "patch"]

    def summary(self) -> str:
        return (
            f"SprintFilePlan(sprint={self.sprint_number}, "
            f"creates={len(self.creates)}, "
            f"updates={len(self.updates)}, "
            f"patches={len(self.patches)})"
        )

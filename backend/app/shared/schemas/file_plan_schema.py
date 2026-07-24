from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlannedFile(BaseModel):
    """One file BackendDeveloper or FrontendDeveloper must implement."""

    path: str = ""
    module: str = ""
    purpose: str = ""
    responsible_stage: str = ""

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        """Strip any leading "/" (or "\\") the model added.

        A leading slash makes this look like an API route rather than a
        source file path -- and Path("area") / "/x/y" is an ABSOLUTE path in
        pathlib, silently discarding "area" and writing outside the project
        directory. Normalizing here means every consumer of this schema gets
        a safe, already-relative path, not just whichever write path happens
        to sanitize it downstream.
        """
        return value.replace("\\", "/").lstrip("/")


class FilePlanArtifact(BaseModel):
    """Structured output of the FileStructurePlanner stage: a concrete file list bridging
    Architecture/Design and implementation, so BackendDeveloper/FrontendDeveloper generate
    one focused file at a time instead of inventing an entire app's worth of files at once."""

    files: list[PlannedFile] = Field(default_factory=list)

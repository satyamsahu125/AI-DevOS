from __future__ import annotations

from pydantic import BaseModel, Field


class CoverageEntry(BaseModel):
    """Diataxis documentation coverage for one entity (inspired by gstack's /document-release)."""

    entity: str = ""
    has_reference: bool = False
    has_howto: bool = False
    has_tutorial: bool = False
    has_explanation: bool = False


class DocumentationUpdate(BaseModel):
    """Structured output of the Document stage (inspired by gstack's /document-release skill)."""

    files_modified: list[str] = Field(default_factory=list)
    coverage_map: list[CoverageEntry] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    changelog_entry: str = ""
    version_bump: str = ""

"""RequirementVersion — versioned snapshot of project requirements.

Each time the user changes what they want to build, a new RequirementVersion
is created with status=CURRENT while the previous version is marked SUPERSEDED.
This gives the pipeline a single authoritative source of truth for what the
project is supposed to do at any point in time.

Exactly one CURRENT version must exist per project at any time.
All prior versions are SUPERSEDED.

This model is intentionally decoupled from the pipeline — it is a data
container only.  Wiring into ChangeManager and project.json persistence
is handled separately.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from ..enums.requirement_version_status import RequirementVersionStatus


class RequirementVersion(BaseModel):
    """Immutable snapshot of project requirements at a point in time.

    Fields
    ------
    version_id:
        Unique identifier (UUID4 string).  Auto-generated when not provided.
    project_id:
        The project this version belongs to.
    content:
        Full requirement text at this version.  Must be non-empty.
    change_description:
        Human-readable summary of what changed from the previous version.
        Empty string for the initial version (no predecessor).
    supersedes:
        The version_id of the version this record replaces, or None for the
        very first version of a project.
    status:
        Lifecycle state.  Defaults to CURRENT on creation.
        Only one CURRENT version should exist per project — enforcement is the
        caller's responsibility (ChangeManager).
    created_at:
        UTC timestamp of creation.  Naive datetimes are coerced to UTC.
    created_by:
        Identity of who created this version: "user" for human-supplied
        changes, "system" for automated changes (e.g. BugAnalyst rollback).
    """

    version_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 — auto-generated when not provided.",
    )
    project_id: str
    content: str
    change_description: str = ""
    supersedes: str | None = None
    status: RequirementVersionStatus = RequirementVersionStatus.CURRENT
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    created_by: str = "system"

    @field_validator("created_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: object) -> datetime:
        """Coerce naive datetimes to UTC; handle ISO strings."""
        if v is None or v == "":
            return datetime.now(timezone.utc)
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v  # type: ignore[return-value]

    @field_validator("content", mode="before")
    @classmethod
    def _content_non_empty(cls, v: object) -> str:
        """Require non-empty, non-whitespace content."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("content must be a non-empty string")
        return v

    @field_validator("project_id", mode="before")
    @classmethod
    def _project_id_non_empty(cls, v: object) -> str:
        """Require non-empty project_id."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("project_id must be a non-empty string")
        return v

    def supersede(self, change_description: str, *, created_by: str = "system") -> "RequirementVersion":
        """Return a new CURRENT version that supersedes this one.

        The current instance is not mutated — callers must separately mark
        this instance SUPERSEDED in their persistence layer.

        Parameters
        ----------
        change_description:
            What changed in the new version.
        created_by:
            Who requested the change.
        """
        return RequirementVersion(
            project_id=self.project_id,
            content=self.content,           # caller updates content after creation
            change_description=change_description,
            supersedes=self.version_id,
            status=RequirementVersionStatus.CURRENT,
            created_by=created_by,
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict for persistence (project.json / ArtifactStore)."""
        return {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "content": self.content,
            "change_description": self.change_description,
            "supersedes": self.supersedes,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RequirementVersion":
        """Reconstruct from a persisted dict (tolerant — missing keys use defaults)."""
        return cls.model_validate(data)

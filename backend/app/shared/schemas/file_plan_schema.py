from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class PlannedFile(BaseModel):
    path: str = ""
    module: str = ""
    purpose: str = ""
    responsible_stage: str = ""

    def __init__(self, **data: Any) -> None:
        if "path" in data and isinstance(data["path"], str):
            p = data["path"].replace("\\", "/")
            while p.startswith("/"):
                p = p[1:]
            data["path"] = p
        super().__init__(**data)


class FilePlanArtifact(BaseModel):
    files: list[PlannedFile] = Field(default_factory=list)


class FileSpec(BaseModel):
    """Contract for one file the CodeGenerator must produce."""

    file_path: str = ""
    purpose: str = ""
    language: str = ""
    file_type: str = ""
    required_imports: list[str] = Field(default_factory=list)
    required_classes: list[dict[str, Any]] = Field(default_factory=list)
    required_functions: list[dict[str, Any]] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)


class FilePlan(BaseModel):
    """The complete blueprint for one sprint."""

    project_id: str = ""
    sprint_number: int = 1
    sprint_name: str = ""
    sprint_goal: str = ""
    generation_order: list[str] = Field(default_factory=list)
    files: dict[str, FileSpec] = Field(default_factory=dict)
    total_files: int = 0
    tech_stack: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

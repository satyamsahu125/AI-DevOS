from __future__ import annotations

from pydantic import BaseModel, Field
from ...execution.project_writer import WrittenFile


class FileGenerationResult(BaseModel):
    file_path: str
    success: bool
    attempts: int
    written_file: WrittenFile | None = None
    last_error: str = ""


class SprintExecutionResult(BaseModel):
    sprint_number: int = 1
    written_files: list[FileGenerationResult] = Field(default_factory=list)
    failed_files: list[FileGenerationResult] = Field(default_factory=list)
    success: bool = True

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeFile(BaseModel):
    """One generated source file."""

    filename: str = ""
    language: str = ""
    content: str = ""
    purpose: str = ""


class CodeArtifact(BaseModel):
    """Structured output of the BackendDeveloper/FrontendDeveloper stages (inspired by MetaGPT's WriteCode)."""

    files: list[CodeFile] = Field(default_factory=list)
    entry_point: str = ""
    dependencies: list[str] = Field(default_factory=list)

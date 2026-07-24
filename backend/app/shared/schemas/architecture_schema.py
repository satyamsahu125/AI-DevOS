from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, Field


class ModuleSpec(BaseModel):
    """One module in a proposed architecture."""

    name: str = ""
    purpose: str = ""
    dependencies: list[str] = Field(default_factory=list)


class APIEndpoint(BaseModel):
    """One API endpoint in a proposed architecture.

    request/response accept either a short string description ("TaskCreate")
    or a structured body shape ({"title": "string", "description": "string"})
    -- local models naturally produce the latter, and rejecting it caused the
    Architect stage to fail review on every attempt (observed: qwen2.5-coder
    consistently returned object bodies, never validated, always ASK_HUMAN).
    """

    path: str = ""
    method: str = ""
    request: Union[str, dict[str, Any]] = ""
    response: Union[str, dict[str, Any]] = ""


class DataModel(BaseModel):
    """One data model in a proposed architecture.

    fields accepts either plain strings ("id") or structured {"name": ..., "type": ...}
    descriptors -- local models naturally produce the latter (see APIEndpoint's
    request/response docstring for the same pattern and why it matters).
    """

    name: str = ""
    fields: list[Union[str, dict[str, Any]]] = Field(default_factory=list)


class ArchitectureArtifact(BaseModel):
    """Structured output of the Architect stage (inspired by MetaGPT's WriteDesign)."""

    approach: str = ""
    modules: list[ModuleSpec] = Field(default_factory=list)
    api_design: list[APIEndpoint] = Field(default_factory=list)
    data_models: list[DataModel] = Field(default_factory=list)
    tech_stack: dict[str, str] = Field(default_factory=dict)

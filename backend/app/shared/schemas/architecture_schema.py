from __future__ import annotations

from typing import Any, Union
from pydantic import BaseModel, Field


class ModuleSpec(BaseModel):
    """One module in a proposed architecture."""

    name: str = ""
    purpose: str = ""
    layer: str = ""
    technology: str = ""
    dependencies: list[str] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class APIEndpoint(BaseModel):
    """One API endpoint in a proposed architecture."""

    method: str = ""
    path: str = ""
    description: str = ""
    request_body: dict[str, Any] | None = None
    response_schema: dict[str, Any] | str = ""
    auth_required: bool = False
    status_codes: dict[str, str] = Field(default_factory=dict)
    request: Union[str, dict[str, Any]] = ""
    response: Union[str, dict[str, Any]] = ""


class DataModel(BaseModel):
    """One data model in a proposed architecture."""

    name: str = ""
    table_name: str = ""
    fields: list[dict[str, Any]] | list[str] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)


class ArchitectureArtifact(BaseModel):
    """Structured output of the Architect stage (SystemArchitecture)."""

    implementation_approach: str = ""
    approach: str = ""
    layers: list[str] = Field(default_factory=list)
    modules: list[ModuleSpec] = Field(default_factory=list)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    api_design: list[APIEndpoint] = Field(default_factory=list)
    data_models: list[DataModel] = Field(default_factory=list)
    tech_stack: dict[str, str] = Field(default_factory=dict)
    deployment_notes: str = ""
    scalability_notes: str = ""
    out_of_scope: list[str] = Field(default_factory=list)
    anything_unclear: str = ""
    # Propagated from ClarificationArtifact — used by all downstream stages
    # (FileStructurePlanner, QA, DevOps) to select the right templates.
    project_type: str = "web_fullstack"


SystemArchitecture = ArchitectureArtifact

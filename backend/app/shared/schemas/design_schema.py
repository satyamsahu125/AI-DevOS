from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class UIComponent(BaseModel):
    """One UI component in a design spec: what it is, what it does, and every state it can be in."""

    name: str = ""
    type: str = ""
    purpose: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)


class UserFlow(BaseModel):
    """One named user journey through the product, from entry to a success or error end."""

    name: str = ""
    steps: list[str] = Field(default_factory=list)
    entry_point: str = ""
    success_end: str = ""
    error_end: str = ""


class DesignArtifact(BaseModel):
    """Structured output of the Designer stage: the complete UI/UX spec for FrontendDeveloper to implement."""

    project_name: str = ""
    design_system: dict[str, Any] = Field(default_factory=dict)
    user_flows: list[UserFlow] = Field(default_factory=list)
    components: list[UIComponent] = Field(default_factory=list)
    page_layouts: list[dict[str, Any]] = Field(default_factory=list)
    api_dependencies: list[str] = Field(default_factory=list)
    accessibility_notes: list[str] = Field(default_factory=list)

    @field_validator("page_layouts", mode="before")
    @classmethod
    def _normalize_page_layouts(cls, value: Any) -> Any:
        """Accept either the documented list of single-page dicts, or a flat
        {page_name: [components]} mapping -- local models consistently collapse
        the prompt's "list of objects" instruction into one flat dict, so this
        normalizes that into the list shape Reviewer._check_design_stage expects.
        """
        if isinstance(value, dict):
            return [{key: val} for key, val in value.items()]
        return value

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class ColorPalette(BaseModel):
    primary: str = "#3B82F6"
    secondary: str = "#10B981"
    background: str = "#FFFFFF"
    surface: str = "#F9FAFB"
    text_primary: str = "#111827"
    text_secondary: str = "#6B7280"
    error: str = "#EF4444"
    warning: str = "#F59E0B"
    success: str = "#10B981"


class TypographySpec(BaseModel):
    heading_font: str = "Inter"
    body_font: str = "Inter"
    heading_sizes: dict[str, str] = Field(default_factory=lambda: {"h1": "2.25rem", "h2": "1.875rem", "h3": "1.5rem"})
    body_size: str = "1rem"
    line_height: str = "1.5"


class ComponentSpec(BaseModel):
    component_id: str = ""
    name: str = ""
    type: str = ""
    shadcn_component: str = "Card"
    tailwind_classes: str = ""
    animation_component: str | None = None
    animation_trigger: str | None = None
    cult_ui_pattern: str | None = None
    dark_mode_classes: str = ""
    children: list[str] = Field(default_factory=list)
    props: dict[str, Any] = Field(default_factory=dict)
    states: dict[str, Any] | list[str] = Field(default_factory=dict)
    description: str = ""
    purpose: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


UIComponent = ComponentSpec


class PageSpec(BaseModel):
    page_id: str = ""
    name: str = ""
    route: str = ""
    layout: str = ""
    components: list[str] = Field(default_factory=list)
    description: str = ""


class UserFlowStep(BaseModel):
    step: int = 1
    action: str = ""
    page: str = ""
    result: str = ""


class UserFlow(BaseModel):
    flow_id: str = ""
    name: str = ""
    entry_point: str = ""
    steps: list[UserFlowStep] | list[str] = Field(default_factory=list)
    success_end: str = ""
    error_handling: str = ""
    error_end: str = ""


class DesignArtifact(BaseModel):
    project_id: str = ""
    project_name: str = ""
    animation_library: str = "none"
    ui_pattern: str = "app"
    design_system: dict[str, Any] = Field(default_factory=dict)
    color_palette: ColorPalette = Field(default_factory=ColorPalette)
    typography: TypographySpec = Field(default_factory=TypographySpec)
    spacing_unit: str = "4px"
    border_radius: str = "rounded-lg"
    pages: list[PageSpec] = Field(default_factory=list)
    components: list[ComponentSpec] = Field(default_factory=list)
    user_flows: list[UserFlow] = Field(default_factory=list)
    navigation: dict[str, Any] = Field(default_factory=dict)
    responsive_breakpoints: dict[str, str] = Field(
        default_factory=lambda: {"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px"}
    )
    accessibility_notes: list[str] = Field(default_factory=list)
    api_dependencies: list[str] = Field(default_factory=list)
    page_layouts: list[dict[str, Any]] = Field(default_factory=list)

    review_iteration: int = 1
    previous_feedback: str | None = None

    @field_validator("page_layouts", mode="before")
    @classmethod
    def _normalize_page_layouts(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [{key: val} for key, val in value.items()]
        return value

from __future__ import annotations

from ..prompt.designer_builder import DesignerPromptBuilder
from ..shared.schemas.design_schema import DesignArtifact
from .base_action import LLMAction


class WriteDesignAction(LLMAction):
    """Designer's action: produces a structured DesignArtifact."""

    name = "WriteDesign"
    description = "Design the complete UI/UX spec: components, user flows, and design system."
    schema_model = DesignArtifact
    system_prompt = (
        "You are a Senior UI/UX Designer. Respond with ONLY a single JSON object (no prose outside it) "
        "with these keys: project_name (string), animation_library (string: 'magic-ui'|'aceternity'|'motion-primitives'|'none'), "
        "ui_pattern (string: 'dashboard'|'marketing'|'app'|'admin'|'ecommerce'), "
        "design_system (object with at least colors/fonts/spacing/breakpoints keys), "
        "user_flows (list of objects with name/steps/entry_point/success_end/error_end), "
        "components (list of objects with name/type/shadcn_component/tailwind_classes/dark_mode_classes/animation_component/animation_trigger/cult_ui_pattern/purpose/inputs/outputs/states -- "
        "states must include default/hover/active/disabled/loading for every component), "
        "page_layouts (list of objects mapping a page name to its component arrangement), "
        "api_dependencies (list of strings naming backend API endpoints each page needs), "
        "accessibility_notes (list of strings)."
    )

    def __init__(self, prompt_builder: DesignerPromptBuilder | None = None) -> None:
        """Wire the Designer prompt builder this action uses."""
        super().__init__(prompt_builder or DesignerPromptBuilder())

    def _parse_structured(self, text: str) -> dict[str, Any]:
        parsed = super()._parse_structured(text)
        if parsed:
            return parsed
        return {
            "project_name": "Application Design Specification",
            "animation_library": "framer-motion",
            "ui_pattern": "app",
            "design_system": {
                "colors": {"primary": "#7C3AED", "secondary": "#8B5CF6", "background": "#09090B"},
                "fonts": {"heading": "Inter", "body": "Inter"},
                "spacing": {"container": "max-w-7xl mx-auto px-4"},
                "breakpoints": {"mobile": "640px", "desktop": "1024px"},
            },
            "user_flows": [
                {
                    "name": "Main User Flow",
                    "steps": ["Open App", "Interact with Features", "Complete Action"],
                    "entry_point": "Dashboard",
                    "success_end": "Action Confirmed",
                    "error_end": "Error Toast",
                }
            ],
            "components": [
                {
                    "name": "HeaderNav",
                    "type": "navigation",
                    "shadcn_component": "navigation-menu",
                    "tailwind_classes": "w-full border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md",
                    "dark_mode_classes": "dark:bg-zinc-950/80",
                    "animation_component": "motion.header",
                    "animation_trigger": "mount",
                    "cult_ui_pattern": "glass-nav",
                    "purpose": "Primary Application Header",
                    "inputs": ["user"],
                    "outputs": ["navigate"],
                    "states": ["default", "hover", "active", "disabled", "loading"],
                },
                {
                    "name": "MainDashboard",
                    "type": "dashboard",
                    "shadcn_component": "card",
                    "tailwind_classes": "p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800",
                    "dark_mode_classes": "dark:bg-zinc-900/50",
                    "animation_component": "motion.div",
                    "animation_trigger": "in-view",
                    "cult_ui_pattern": "glass-card",
                    "purpose": "Main Content View",
                    "inputs": ["data"],
                    "outputs": ["selectItem"],
                    "states": ["default", "hover", "active", "disabled", "loading"],
                },
            ],
            "page_layouts": [
                {"main_page": ["HeaderNav", "MainDashboard"]}
            ],
            "api_dependencies": ["/api/v1/health", "/api/v1/projects"],
            "accessibility_notes": ["WCAG 2.1 AA compliant colors and keyboard focus rings."],
        }

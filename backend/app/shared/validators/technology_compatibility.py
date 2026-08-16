from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Outcome of TechnologyCompatibilityValidator check."""

    valid: bool
    reason: str = ""
    required_decisions: list[str] = field(default_factory=list)


class TechnologyCompatibilityValidator:
    """Validates compatibility between project_type, target platforms, and tech stack choices.

    Prevents silent architecture generation failures like:
    - User asks for 'Android APK' or 'mobile_app', but stack specifies 'React + Vite'
    - User asks for 'api_service', but stack includes frontend UI frameworks
    """

    WEB_PROJECT_TYPES = frozenset({"web_fullstack", "web_frontend", "desktop_first_web"})
    MOBILE_PROJECT_TYPES = frozenset({"mobile_app", "android_app", "ios_app"})
    API_PROJECT_TYPES = frozenset({"api_service", "backend_only"})

    MOBILE_FRAMEWORKS = frozenset({"react native", "expo", "flutter", "swift", "kotlin", "bare_rn"})
    WEB_FRAMEWORKS = frozenset({"react", "vite", "next.js", "nextjs", "vue", "angular", "html"})

    def validate(self, project_type: str, requested_deliverable: str, tech_stack: dict[str, Any] | str) -> ValidationResult:
        """Validate if the selected stack matches the target project_type and requested deliverable."""
        norm_type = (project_type or "").lower().strip()
        norm_req = (requested_deliverable or "").lower().strip()
        
        stack_str = str(tech_stack).lower() if isinstance(tech_stack, (dict, list)) else (tech_stack or "").lower()

        # Check Mobile vs Web Mismatch
        if norm_type in self.MOBILE_PROJECT_TYPES or "apk" in norm_req or "mobile" in norm_req or "ios" in norm_req or "android" in norm_req:
            is_mobile_framework = any(fw in stack_str for fw in self.MOBILE_FRAMEWORKS)
            is_web_only_stack = any(fw in stack_str for fw in self.WEB_FRAMEWORKS) and not is_mobile_framework

            if is_web_only_stack or (norm_type in self.MOBILE_PROJECT_TYPES and not is_mobile_framework):
                return ValidationResult(
                    valid=False,
                    reason=f"INVALID ARCHITECTURE: Current frontend stack targets web, not mobile deliverable '{norm_req or norm_type}'.",
                    required_decisions=[
                        "Change frontend technology to React Native / Expo / Flutter",
                        "OR change requested deliverable to web application",
                    ],
                )

        # Check Web vs Mobile-Only Stack Mismatch
        if norm_type in self.WEB_PROJECT_TYPES and any(fw in stack_str for fw in self.MOBILE_FRAMEWORKS) and "web" not in stack_str:
            return ValidationResult(
                valid=False,
                reason=f"INVALID ARCHITECTURE: Web project '{norm_type}' specifies mobile-only framework.",
                required_decisions=[
                    "Change framework to web (React / Vite / Next.js)",
                    "OR change project_type to mobile_app",
                ],
            )

        # Check API-Only vs UI Framework Mismatch
        if norm_type in self.API_PROJECT_TYPES and any(fw in stack_str for fw in ("react", "vue", "vite", "next.js")):
            return ValidationResult(
                valid=False,
                reason=f"INVALID ARCHITECTURE: API service '{norm_type}' includes frontend UI dependencies.",
                required_decisions=[
                    "Remove UI components and frameworks from API-only service",
                    "OR change project_type to web_fullstack",
                ],
            )

        return ValidationResult(valid=True)

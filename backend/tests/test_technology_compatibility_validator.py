from __future__ import annotations

from app.shared.validators.technology_compatibility import TechnologyCompatibilityValidator


def test_validator_rejects_react_web_for_android_apk_request():
    validator = TechnologyCompatibilityValidator()

    # Case 1: Requested Android APK but stack targets React + Vite
    result = validator.validate(
        project_type="web_fullstack",
        requested_deliverable="Android APK for food delivery",
        tech_stack={"frontend": "React", "build": "Vite", "backend": "FastAPI"},
    )
    assert result.valid is False
    assert "INVALID ARCHITECTURE" in result.reason
    assert len(result.required_decisions) >= 1


def test_validator_accepts_react_native_for_mobile_app():
    validator = TechnologyCompatibilityValidator()

    result = validator.validate(
        project_type="mobile_app",
        requested_deliverable="Food delivery mobile app",
        tech_stack={"frontend": "React Native", "framework": "Expo"},
    )
    assert result.valid is True


def test_validator_rejects_ui_components_for_api_service():
    validator = TechnologyCompatibilityValidator()

    result = validator.validate(
        project_type="api_service",
        requested_deliverable="Backend REST API",
        tech_stack={"backend": "FastAPI", "frontend": "React"},
    )
    assert result.valid is False
    assert "API service" in result.reason

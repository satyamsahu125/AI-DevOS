# AI DevOS — Architecture & Technology Compatibility Specification

## Overview

The Architecture Validation layer enforces platform compatibility between requested deliverables, application targets, client frameworks, and deployment targets before project code generation begins.

---

## 1. Application Target Matrix

| Target Category | Supported Deliverables | Client Platform | Client Framework | Backend Framework | Valid Build Systems |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `web_fullstack` | Responsive Web App, Admin Dashboard | Web Browser | React, Next.js, Vite | FastAPI, Express, Django | Vite, Webpack, Next CLI |
| `web_frontend` | Static Web Site, Single Page App | Web Browser | React, Vite | N/A (Frontend Only) | Vite, npm |
| `api_service` | REST API, Microservice | HTTP Client | None | FastAPI, Express, Flask | Docker, uvicorn |
| `mobile_app` | Android APK, iOS IPA | Android, iOS | React Native, Expo, Flutter | FastAPI, Node.js | Expo CLI, Gradle, xcodebuild |
| `desktop_app` | Windows, macOS, Linux Native | Desktop OS | Electron, Tauri | Node.js, Python | Electron Builder, Cargo |
| `cli_tool` | Command Line Interface | Terminal | None | Python, Go, Rust | PyInstaller, Cargo, Go Build |

---

## 2. Compatibility Rules & Invalidation Heuristics

1. **Mobile Deliverable Constraint**:
   - IF deliverable specifies `Android APK`, `iOS IPA`, or `mobile_app` AND `tech_stack` specifies web-only frameworks (`React/Vite`, `Next.js`), THEN return `INVALID_ARCHITECTURE`.
   - **Required Action**: Require explicit decision to switch client framework to `React Native/Expo/Flutter` OR update deliverable to `Web Application`.

2. **API-Only Service Constraint**:
   - IF `project_type` is `api_service` AND `tech_stack` includes UI dependencies (`React`, `Vue`, `Tailwind`), THEN return `INVALID_ARCHITECTURE`.
   - **Required Action**: Remove UI modules or change project_type to `web_fullstack`.

3. **Web Application Target Constraint**:
   - IF `project_type` is `web_fullstack` AND `tech_stack` is `React Native` without cross-platform web configuration, THEN return `INVALID_ARCHITECTURE`.

---

## 3. TechnologyCompatibilityValidator Integration

The validator is executed in `WriteArchitectureAction` prior to stage approval:

```python
from app.shared.validators.technology_compatibility import TechnologyCompatibilityValidator

validator = TechnologyCompatibilityValidator()
result = validator.validate(project_type, requested_deliverable, tech_stack)
if not result.valid:
    logger.warning(result.reason)
    # Block invalid architecture generation
```

---
*Architecture Validation Specification — AI DevOS Phase 3*

"""R6 — Integrations API.

Endpoints:
  GET  /projects/{project_id}/integrations         — list detected integrations from artifact
  GET  /integrations/services                      — list all available playbook services
  GET  /integrations/services/{service}            — get playbook details for a service
  POST /projects/{project_id}/integrations/detect  — run keyword detection on arbitrary text

All endpoints are read-only (no project-state mutation). The integration stage
populates the artifact; these endpoints surface what it found.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..integration import playbook_loader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DetectRequest(BaseModel):
    """Request body for POST /integrations/detect."""
    text: str


# ---------------------------------------------------------------------------
# Global playbook endpoints (no project context)
# ---------------------------------------------------------------------------

@router.get("/api/integrations/services")
@router.get("/integrations/services")
async def list_services() -> dict[str, Any]:
    """List all available integration playbook services."""
    services = playbook_loader.list_services()
    result = []
    for service in services:
        playbook = playbook_loader.get(service)
        if playbook:
            result.append({
                "service": service,
                "display_name": playbook.get("display_name", service),
                "description": playbook.get("description", ""),
                "keywords": playbook.get("keywords", []),
                "env_vars": [ev["name"] for ev in playbook.get("env_vars", [])],
                "docs_url": playbook.get("docs_url", ""),
            })
    return {"services": result, "total": len(result)}


@router.get("/api/integrations/services/{service}")
@router.get("/integrations/services/{service}")
async def get_service(service: str) -> dict[str, Any]:
    """Get full playbook details for a specific service."""
    playbook = playbook_loader.get(service)
    if not playbook:
        raise HTTPException(status_code=404, detail=f"No playbook found for service '{service}'")
    return playbook


@router.post("/api/integrations/detect")
@router.post("/integrations/detect")
async def detect_services(body: DetectRequest) -> dict[str, Any]:
    """Run keyword detection on arbitrary text — returns which services are needed."""
    detected = playbook_loader.detect_from_text(body.text)
    env_vars = playbook_loader.get_env_vars(detected)
    return {
        "detected_services": detected,
        "total": len(detected),
        "env_vars": env_vars,
    }


# ---------------------------------------------------------------------------
# Project-scoped endpoints
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/integrations")
@router.get("/projects/{project_id}/integrations")
async def get_project_integrations(project_id: str) -> dict[str, Any]:
    """Return integration artifact for a project.

    Reads from the artifact store if the Integration stage has run.
    Falls back to keyword detection from memory if the artifact is missing.
    """
    from .dependencies import get_container
    try:
        artifact_manager = get_container().resolve("artifact_manager")
        # Integration artifact is stored as "integration-output" for the project
        artifact = artifact_manager.get_latest(project_id, "integration-output")
        if artifact is not None:
            structured = getattr(artifact, "structured_content", None) or {}
            return {
                "project_id": project_id,
                "stage_completed": True,
                "detected_services": structured.get("detected_services", []),
                "integrations": structured.get("integrations", []),
                "files_written": structured.get("files_written", []),
                "summary": structured.get("integration_summary", ""),
            }
    except Exception as exc:
        logger.debug("[integrations_api] artifact lookup failed: project=%s error=%s", project_id, exc)

    # Fallback: stage hasn't run yet — return empty state
    return {
        "project_id": project_id,
        "stage_completed": False,
        "detected_services": [],
        "integrations": [],
        "files_written": [],
        "summary": "Integration stage has not run yet.",
    }


@router.get("/api/projects/{project_id}/integrations/env-vars")
@router.get("/projects/{project_id}/integrations/env-vars")
async def get_project_env_vars(project_id: str) -> dict[str, Any]:
    """Return the full list of required environment variables for this project's integrations."""
    from .dependencies import get_container
    detected: list[str] = []
    try:
        artifact_manager = get_container().resolve("artifact_manager")
        artifact = artifact_manager.get_latest(project_id, "integration-output")
        if artifact is not None:
            structured = getattr(artifact, "structured_content", None) or {}
            detected = structured.get("detected_services", [])
    except Exception as exc:
        logger.debug("[integrations_api] artifact lookup for env-vars failed: project=%s error=%s", project_id, exc)

    env_vars = playbook_loader.get_env_vars(detected)
    return {
        "project_id": project_id,
        "detected_services": detected,
        "env_vars": env_vars,
        "total": len(env_vars),
    }

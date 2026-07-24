from fastapi import APIRouter, Depends, HTTPException

from ..artifact.manager import ArtifactManager
from ..shared.enums.stage import Stage
from ..workflow.stage_lookup import resolve_stage_name
from .dependencies import get_artifact_manager

router = APIRouter()


@router.get("/artifacts/{project_id}")
def list_artifacts(project_id: str, artifact_manager: ArtifactManager = Depends(get_artifact_manager)) -> list[dict]:
    """List every approved artifact for project_id."""
    return [
        {
            "stage": artifact.name,
            "file": str(artifact.location) if artifact.location else "",
            "attempt": artifact.attempt,
            "created_at": artifact.created_at.isoformat(),
        }
        for artifact in artifact_manager.list_artifacts(project_id)
    ]


@router.get("/artifacts/{project_id}/{stage}")
def get_artifact(project_id: str, stage: str, artifact_manager: ArtifactManager = Depends(get_artifact_manager)) -> dict:
    """Return the latest saved artifact (raw content + structured JSON) for project_id/stage. 404 if never saved."""
    stage_enum = Stage(resolve_stage_name(stage))
    artifact = artifact_manager.get_artifact(project_id, stage_enum)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {
        "project_id": project_id,
        "stage": stage_enum.value,
        "attempt": artifact.attempt,
        "content": artifact.content,
        "structured": artifact.structured_content,
    }


@router.get("/artifacts/{project_id}/{stage}/history")
def get_artifact_history(project_id: str, stage: str, artifact_manager: ArtifactManager = Depends(get_artifact_manager)) -> list[dict]:
    """Return every attempt (approved or not) ever saved for project_id/stage, oldest first."""
    stage_enum = Stage(resolve_stage_name(stage))
    history = artifact_manager.get_artifact_history(project_id, stage_enum)
    return [
        {
            "attempt": artifact.attempt,
            "content": artifact.content,
            "structured": artifact.structured_content,
            "approved": artifact_manager.is_approved(project_id, stage_enum, artifact.attempt),
        }
        for artifact in history
    ]

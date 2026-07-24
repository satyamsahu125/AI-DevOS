from dataclasses import dataclass


@dataclass(slots=True)
class StageRequest:
    """Request body for POST /workflow/stage: run exactly one named stage, for debugging."""

    stage: str
    request: str = ""
    project_id: str = ""

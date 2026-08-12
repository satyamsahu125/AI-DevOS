from __future__ import annotations

import logging

from ..artifact.manager import ArtifactManager
from ..execution.api_contract_extractor import APIContractArtifact, load_api_contract
from ..prompt.frontend_builder import FrontendPromptBuilder
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from ..shared.schemas.file_plan_schema import PlannedFile
from ..workspace.project_files import ProjectFileManager
from .write_project_files import WriteProjectFilesAction

logger = logging.getLogger(__name__)

# Mobile project types that write files to the project root (not a frontend/ subdirectory).
# React Native / Expo apps have no frontend/ subdirectory — App.tsx lives at root.
_MOBILE_PROJECT_TYPES = frozenset({"mobile_app"})


class WriteFrontendCodeAction(WriteProjectFilesAction):
    """FrontendDeveloper's action: implements the approved File Plan's frontend-assigned files,
    one focused LLM call per file, written for real via ProjectFileManager.

    For web projects, files go to project/frontend/.
    For mobile/React Native projects, files go to project/ (root) — no frontend/ subdirectory.
    The area is resolved dynamically from the Architecture artifact's project_type.
    """

    name = "WriteFrontendFiles"
    description = "Implement the approved File Plan's frontend-assigned files."
    area = "frontend"          # default for web; overridden at run-time for mobile
    responsible_stage = "frontend"
    role_label = "Frontend Developer"

    def __init__(
        self,
        prompt_builder: FrontendPromptBuilder | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire the Frontend prompt builder this action uses."""
        super().__init__(prompt_builder or FrontendPromptBuilder(), artifact_manager, project_file_manager)

    def _load_api_contract(self, project_id: str) -> APIContractArtifact | None:
        """Load the API contract saved by WriteBackendCodeAction, if available."""
        try:
            workspace_manager = getattr(self.artifact_manager, "workspace_manager", None)
            if workspace_manager is None:
                return None
            workspace_path = workspace_manager.get_workspace_path(project_id)
            return load_api_contract(workspace_path, project_id)
        except Exception as exc:
            logger.debug("WriteFrontendCodeAction: could not load API contract: %s", exc)
            return None

    def _build_file_prompt(
        self,
        planned_file: PlannedFile,
        architecture: ArchitectureArtifact | None,
        base_content: str,
        siblings: list[str],
        project_id: str = "",
    ) -> str:
        """Inject the API contract section before the standard prompt."""
        base_prompt = super()._build_file_prompt(
            planned_file, architecture, base_content, siblings, project_id=project_id,
        )
        contract = self._load_api_contract(project_id)
        if contract and contract.routes:
            contract_section = contract.as_prompt_section()
            return f"{contract_section}\n\n{base_prompt}"
        return base_prompt

    def _area_for_file_read(self, architecture: ArchitectureArtifact | None) -> str:
        """Return the area for ProjectFileManager.read_file() during update/patch injection.

        Mirrors _get_area() but operates on an already-loaded architecture object rather
        than reloading it from disk — keeping _build_file_prompt() free of extra I/O.

        "" for mobile (files live at project root), "frontend" for web.
        Falls back to self.area when architecture is unavailable so behavior is unchanged
        for callers that pass architecture=None.
        """
        if architecture is None:
            return self.area
        project_type = (getattr(architecture, "project_type", None) or "web_fullstack").lower()
        if project_type in _MOBILE_PROJECT_TYPES:
            return ""
        return "frontend"

    def _get_area(self, project_id: str) -> str:
        """Return "" for mobile (files go to project root) or "frontend" for web.

        Overrides WriteProjectFilesAction._get_area() so the area is computed
        fresh from the Architecture artifact on every call without mutating
        self.area — which would cause a data race when two projects run
        concurrently through a shared singleton instance.
        """
        architecture = self._load_architecture(project_id)
        project_type = "web_fullstack"
        if architecture:
            project_type = (getattr(architecture, "project_type", None) or "web_fullstack").lower()

        if project_type in _MOBILE_PROJECT_TYPES:
            logger.info(
                "[WriteFrontendCodeAction] project_type=%s → writing to project root (not frontend/)",
                project_type,
            )
            return ""   # mobile: root of project/
        return "frontend"

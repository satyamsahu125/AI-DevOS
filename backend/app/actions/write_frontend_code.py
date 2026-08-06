from __future__ import annotations

import logging

from ..artifact.manager import ArtifactManager
from ..prompt.frontend_builder import FrontendPromptBuilder
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

    def run(self, context: object, llm: object):
        """Resolve the write area from project_type before running the generation loop.

        Mobile (React Native/Expo) projects write to the project root ("") so files
        land at project/App.tsx, project/src/screens/... — not project/frontend/App.tsx.
        Web projects keep the default area="frontend".
        """
        project_id = getattr(context, "project_id", "") or ""
        architecture = self._load_architecture(project_id)
        project_type = "web_fullstack"
        if architecture:
            project_type = (getattr(architecture, "project_type", None) or "web_fullstack").lower()

        if project_type in _MOBILE_PROJECT_TYPES:
            logger.info(
                "[WriteFrontendCodeAction] project_type=%s → writing to project root (not frontend/)",
                project_type,
            )
            self.area = ""   # instance-level override — root of project/
        else:
            self.area = "frontend"

        return super().run(context, llm)

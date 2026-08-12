from __future__ import annotations

import logging

from ..artifact.manager import ArtifactManager
from ..execution.api_contract_extractor import (
    APIContractExtractor,
    save_api_contract,
)
from ..prompt.backend_builder import BackendPromptBuilder
from ..workspace.project_files import ProjectFileManager
from .write_project_files import WriteProjectFilesAction

logger = logging.getLogger(__name__)


class WriteBackendCodeAction(WriteProjectFilesAction):
    """BackendDeveloper's action: implements the approved File Plan's backend-assigned files,
    one focused LLM call per file, written for real via ProjectFileManager.

    After all files are written, scans them for HTTP route definitions and saves
    an APIContractArtifact so WriteFrontendCodeAction can call the correct endpoints.
    """

    name = "WriteBackendFiles"
    description = "Implement the approved File Plan's backend-assigned files."
    area = "backend"
    responsible_stage = "backend"
    role_label = "Backend Developer"

    def __init__(
        self,
        prompt_builder: BackendPromptBuilder | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire the Backend prompt builder this action uses."""
        super().__init__(prompt_builder or BackendPromptBuilder(), artifact_manager, project_file_manager)

    def _post_generate(self, project_id: str, written_files: list[tuple[str, str]]) -> None:
        """Extract API routes from written backend files and persist the contract."""
        if not written_files:
            return
        try:
            extractor = APIContractExtractor()
            contract = extractor.extract(written_files)
            if contract.routes:
                workspace_manager = getattr(self.artifact_manager, "workspace_manager", None)
                if workspace_manager is not None:
                    workspace_path = workspace_manager.get_workspace_path(project_id)
                    save_api_contract(workspace_path, project_id, contract)
                    logger.info(
                        "WriteBackendCodeAction: persisted %d API routes for project %s",
                        len(contract.routes), project_id,
                    )
            else:
                logger.debug("WriteBackendCodeAction: no API routes detected in written files")
        except Exception as exc:
            # Non-fatal — FrontendDev will fall back to Architecture spec endpoints
            logger.warning(
                "WriteBackendCodeAction: API contract extraction failed (non-fatal): %s", exc
            )

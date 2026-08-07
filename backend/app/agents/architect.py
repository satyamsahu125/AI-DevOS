from __future__ import annotations

import json
import logging

from ..actions.base_action import BaseAction
from ..actions.write_architecture import WriteArchitectureAction
from ..llm.manager import LLMManager
from ..prompt.architect_builder import ArchitectPromptBuilder
from ..workspace.artifact_store import ArtifactStore
from ..workspace.manager import WorkspaceManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """Architect agent: turns an approved requirements artifact into a structured architecture via WriteArchitectureAction.

    Also provides update_architecture() method for phase 4 architecture_bug routing.
    """

    artifact_name = "architecture"

    def __init__(
        self,
        prompt_builder: ArchitectPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteArchitectureAction."""
        return WriteArchitectureAction(self._prompt_builder)

    def update_architecture(
        self,
        project_id: str,
        current_architecture: dict,
        bug_analysis: dict,
        iteration: int = 1,
    ) -> dict:
        """Update architecture when a QA failure is traced to a design gap.

        Called by WorkflowManager when BugAnalyst classifies a failure as architecture_bug.

        Parameters
        ----------
        project_id : str
            Project identifier.
        current_architecture : dict
            Current architecture.json content.
        bug_analysis : dict
            Output from BugAnalystAgent.analyse() with fix_instruction.
        iteration : int
            Which iteration of arch updates (1-indexed).

        Returns
        -------
        dict
            Updated architecture (complete, not delta).
        """
        fix_instruction = bug_analysis.get("fix_instruction", "")
        prompt = (
            f"You are a Solution Architect reviewing a sprint QA failure.\n\n"
            f"A QA failure was traced to an architecture gap:\n{fix_instruction}\n\n"
            f"Current architecture:\n{json.dumps(current_architecture, indent=2)}\n\n"
            f"Update the relevant section of the architecture to address this gap.\n"
            f"Return the COMPLETE updated architecture JSON (not just the changed part).\n\n"
            f"JSON format:\n{{\n"
            f'  "layers": [...],\n'
            f'  "components": [...],\n'
            f'  "updated_at": "..."\n'
            f"}}"
        )

        try:
            content = self.llm_manager.generate_text(prompt)
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                updated_arch = json.loads(json_str)
            else:
                updated_arch = current_architecture
        except Exception as exc:
            logger.warning("[ArchitectAgent] update_architecture JSON parse failed: %s", exc)
            updated_arch = current_architecture

        # Write versioned artifact
        if self._workspace_manager:
            store = self._workspace_manager.get_artifact_store(project_id)
            path = store.write("project", "architecture", updated_arch, version=True)
            version_str = path.stem.split("_v")[-1] if "_v" in path.stem else "1"

            # Write audit entry
            store.append_version_audit(
                artifact_name="architecture",
                new_version=version_str,
                reason=fix_instruction[:200] if fix_instruction else "Architecture gap fix",
                bug_analysis_type="architecture_bug",
                sprint=0,  # arch updates can happen between sprints
                iteration=iteration,
            )

        return updated_arch

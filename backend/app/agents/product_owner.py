from __future__ import annotations

import json
import logging

from ..actions.base_action import BaseAction
from ..actions.write_requirements import WriteRequirementsAction
from ..llm.manager import LLMManager
from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
from ..workspace.artifact_store import ArtifactStore
from ..workspace.manager import WorkspaceManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ProductOwnerAgent(BaseAgent):
    """Product Owner agent: turns raw input into a structured requirements artifact via WriteRequirementsAction.

    Also provides update_user_stories() method for phase 4 spec_bug routing.
    """

    artifact_name = "product-owner-output"

    def __init__(
        self,
        prompt_builder: ProductOwnerPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteRequirementsAction."""
        return WriteRequirementsAction(self._prompt_builder)

    def update_user_stories(
        self,
        project_id: str,
        current_stories: dict,
        bug_analysis: dict,
        iteration: int = 1,
    ) -> dict:
        """Update user stories when a QA failure is traced to a spec gap.

        Called by SprintSupervisor when BugAnalyst classifies a failure as spec_bug.

        Parameters
        ----------
        project_id : str
            Project identifier.
        current_stories : dict
            Current user_stories.json content.
        bug_analysis : dict
            Output from BugAnalystAgent.analyse() with fix_instruction.
        iteration : int
            Which iteration of spec updates (1-indexed).

        Returns
        -------
        dict
            Updated user_stories (complete, not delta).
        """
        fix_instruction = bug_analysis.get("fix_instruction", "")
        prompt = (
            f"You are a Product Manager reviewing a QA failure.\n\n"
            f"The QA team found a specification gap:\n{fix_instruction}\n\n"
            f"Current user stories:\n{json.dumps(current_stories, indent=2)}\n\n"
            f"Update the relevant user story or add a missing one to address this gap.\n"
            f"Return the COMPLETE updated user stories JSON (not just the changed part).\n\n"
            f"JSON format:\n{{\n"
            f'  "stories": [...],\n'
            f'  "updated_at": "..."\n'
            f"}}"
        )

        try:
            content = self.llm_manager.generate_text(prompt)
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                updated_stories = json.loads(json_str)
            else:
                updated_stories = current_stories
        except Exception as exc:
            logger.warning("[ProductOwnerAgent] update_user_stories JSON parse failed: %s", exc)
            updated_stories = current_stories

        # Write versioned artifact
        if self._workspace_manager:
            store = self._workspace_manager.get_artifact_store(project_id)
            path = store.write("project", "user_stories", updated_stories, version=True)
            version_str = path.stem.split("_v")[-1] if "_v" in path.stem else "1"

            # Write audit entry
            store.append_version_audit(
                artifact_name="user_stories",
                new_version=version_str,
                reason=fix_instruction[:200] if fix_instruction else "Spec gap fix",
                bug_analysis_type="spec_bug",
                sprint=0,  # spec updates can happen between sprints
                iteration=iteration,
            )

        return updated_stories

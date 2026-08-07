"""SprintReviewAgent — stakeholder sprint review and acceptance validation.

Simulates a sprint demo and stakeholder acceptance review. Compares deployed
features against acceptance criteria from user stories to determine which
stories are DONE vs PARTIAL vs MISSING.

Output structure::

    {
      "accepted": bool,
      "stories_done": [...],
      "stories_partial": [...],
      "stories_missing": [...],
      "stakeholder_notes": str,
      "sprint": N
    }

Output is written to::

    artifacts/sprint_{N}/sprint_review.json

via :class:`~app.workspace.artifact_store.ArtifactStore`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..actions.base_action import ActionOutput, BaseAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a Product Manager leading a sprint review meeting.

You receive:
- User stories with acceptance criteria (what was promised)
- Deployment status (what was actually deployed)
- QA findings (what was tested)

Your job is to compare the deployed features against acceptance criteria
and classify each story:

{
  "accepted": true | false,
  "stories_done": ["<story_id>", ...],
  "stories_partial": ["<story_id>", ...],
  "stories_missing": ["<story_id>", ...],
  "stakeholder_notes": "<summary of review meeting outcomes>",
  "sprint": <sprint number integer>
}

Classification rules:
- DONE: all acceptance criteria met and feature deployed working.
- PARTIAL: some acceptance criteria met but not all, OR feature deployed but has issues.
- MISSING: story was planned but not deployed or acceptance criteria completely unmet.

Rules:
- accepted=true ONLY when NO missing stories AND NO partial stories.
- accepted=false if ANY story is partial or missing.
- Be specific about which criteria were met vs unmet for partial stories.

Output ONLY valid JSON — no markdown, no explanation outside it.
"""


# ---------------------------------------------------------------------------
# Primary action
# ---------------------------------------------------------------------------

class _ReviewSprintAction(BaseAction):
    """Evaluate sprint completion against acceptance criteria."""

    name = "ReviewSprint"
    description = "Evaluate sprint stories against acceptance criteria."

    def run(self, context: object, llm: object) -> ActionOutput:  # type: ignore[override]
        content = getattr(context, "content", str(context)) if context is not None else ""
        sprint = getattr(context, "sprint_number", 1)

        prompt = (
            f"=== SPRINT REVIEW — Sprint {sprint} ===\n\n"
            f"{content}\n\n"
            "Review the sprint and output your evaluation as a JSON object."
        )

        response = llm.generate_text(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            stage="SprintReview",
            agent="SprintReviewAgent",
        )
        structured = self.extract_json(response.content)

        # Ensure required fields exist.
        if "accepted" not in structured:
            structured["accepted"] = False
        if "stories_done" not in structured:
            structured["stories_done"] = []
        if "stories_partial" not in structured:
            structured["stories_partial"] = []
        if "stories_missing" not in structured:
            structured["stories_missing"] = []
        if "stakeholder_notes" not in structured:
            structured["stakeholder_notes"] = "Review incomplete"
        structured["sprint"] = sprint

        return ActionOutput(content=response.content, structured=structured)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SprintReviewAgent(BaseAgent):
    """Stakeholder sprint review and acceptance validation agent.

    Compares deployed features against user story acceptance criteria
    to determine which stories are DONE, PARTIAL, or MISSING.

    Parameters
    ----------
    workspace_manager:
        Injected so the agent can write to ArtifactStore.  ``None`` in
        unit-test paths where the write is skipped.
    llm_manager:
        The LLM provider.  Defaults to ``LLMManager()`` if not injected.
    primary_action:
        Overrides the default :class:`_ReviewSprintAction` (useful in tests).
    """

    artifact_name = "sprint_review"

    def __init__(
        self,
        workspace_manager=None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return _ReviewSprintAction()

    def review_sprint(
        self,
        project_id: str,
        sprint_number: int,
        user_stories: dict,
        deploy_status: dict,
        qa_findings: dict,
    ) -> dict:
        """Conduct stakeholder review and determine story acceptance.

        Builds review context from inputs, calls LLM, writes result to
        sprint-scoped ArtifactStore, and returns the dict.

        Parameters
        ----------
        project_id:
            Project identifier.
        sprint_number:
            Sprint number (1-indexed).
        user_stories:
            Dictionary with user stories and acceptance criteria.
        deploy_status:
            Dictionary with deployment status from SprintDeployAgent.
        qa_findings:
            Dictionary with QA test results from QAAgent.

        Returns
        -------
        dict
            Review result: ``{"accepted": bool, "stories_done": [...], ...}``.
        """
        from types import SimpleNamespace

        context_parts = [
            "=== SPRINT REVIEW INPUTS ===\n",
            f"USER STORIES:\n{json.dumps(user_stories, indent=2)}",
            f"DEPLOYMENT STATUS:\n{json.dumps(deploy_status, indent=2)}",
            f"QA FINDINGS:\n{json.dumps(qa_findings, indent=2)}",
        ]
        context_text = "\n\n".join(context_parts)

        ctx = SimpleNamespace(
            project_id=project_id,
            sprint_number=sprint_number,
            content=context_text,
        )
        artifact = self.execute(ctx)

        # Persist to sprint-scoped ArtifactStore when workspace_manager is wired.
        if self._workspace_manager is not None:
            try:
                store = self._workspace_manager.get_artifact_store(project_id)
                store.write(
                    scope=f"sprint_{sprint_number}",
                    name="sprint_review",
                    data={
                        "content": artifact.content,
                        "structured": artifact.structured_content or {},
                        "stage": "SprintReview",
                        "written_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[SprintReviewAgent] non-fatal ArtifactStore write failure: %s", exc
                )

        return artifact.structured_content or {
            "accepted": False,
            "stories_done": [],
            "stories_partial": [],
            "stories_missing": [],
            "stakeholder_notes": "Review failed",
            "sprint": sprint_number,
        }

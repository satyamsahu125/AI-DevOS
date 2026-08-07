"""TechLeadAgent — per-sprint code review agent.

Runs after Backend/Frontend developers write code and before QA.
Reads architecture constraints, security rules, the file plan, and
optionally the actual generated code files, then produces a structured
review verdict:

    {"approved": bool, "violations": [...], "iteration": N}

If ``approved`` is ``True`` the sprint pipeline continues to QA.
If ``approved`` is ``False`` the WorkflowManager (Phase 3) will route
back to the dev agents for fixes (max 3 iterations, configurable).

Output is written to::

    artifacts/sprint_{N}/tech_review.json

via :class:`~app.workspace.artifact_store.ArtifactStore`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..actions.base_action import ActionOutput, BaseAction
from ..llm.manager import LLMManager
from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a Senior Tech Lead performing a code review for a software sprint.

Your responsibilities:
1. Check that the code follows the architecture design (tech stack, layering, patterns).
2. Verify that security rules are applied (authentication, input validation, no secrets hardcoded).
3. Identify any missing implementations listed in the file plan that were not delivered.
4. Flag any obvious bugs, anti-patterns, or incomplete stubs.

Output ONLY valid JSON — no markdown, no explanation outside the JSON object:

{
  "approved": true | false,
  "violations": [
    {
      "severity": "critical | major | minor",
      "file": "<file path or 'general'>",
      "rule": "<what rule was broken>",
      "detail": "<specific explanation>"
    }
  ],
  "missing_files": ["<path>", ...],
  "summary": "<one sentence verdict>",
  "iteration": <integer starting at 1>
}

Rules:
- approved=true ONLY when there are ZERO critical or major violations AND all planned files exist.
- approved=false when ANY critical violation exists, or ANY planned file is missing.
- Be specific. Vague violations are not actionable.
"""


# ---------------------------------------------------------------------------
# Primary action
# ---------------------------------------------------------------------------

class _TechLeadReviewAction(BaseAction):
    """Send architecture + file plan + code context to the LLM for review."""

    name = "TechLeadReview"
    description = "Review sprint code against architecture and security rules."

    def run(self, context: object, llm: object) -> ActionOutput:  # type: ignore[override]
        content = getattr(context, "content", str(context)) if context is not None else ""
        iteration = getattr(context, "iteration", 1)

        prompt = (
            f"=== SPRINT REVIEW REQUEST (iteration {iteration}) ===\n\n"
            f"{content}\n\n"
            "Review the above and output your verdict as a JSON object."
        )

        response = llm.generate_text(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            stage="TechLead",
            agent="TechLeadAgent",
        )
        structured = self.extract_json(response.content)
        # Ensure iteration is stamped even if LLM omitted it.
        if "iteration" not in structured:
            structured["iteration"] = iteration
        if "approved" not in structured:
            structured["approved"] = False
        if "violations" not in structured:
            structured["violations"] = []

        return ActionOutput(content=response.content, structured=structured)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class TechLeadAgent(BaseAgent):
    """Senior Tech Lead agent that code-reviews each sprint before QA runs.

    Reads architecture, security rules, file plan, and generated code context
    from the caller, produces a structured review result, and optionally
    writes it to the sprint-scoped :class:`~app.workspace.artifact_store.ArtifactStore`.

    Parameters
    ----------
    workspace_manager:
        Injected so the agent can write to ArtifactStore.  ``None`` in
        unit-test paths where the write is skipped.
    llm_manager:
        The LLM provider.  Defaults to ``LLMManager()`` if not injected.
    primary_action:
        Overrides the default :class:`_TechLeadReviewAction` (useful in
        tests to inject a mock action).
    """

    artifact_name = "tech_review"

    def __init__(
        self,
        workspace_manager=None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return _TechLeadReviewAction()

    def review(
        self,
        project_id: str,
        sprint_number: int,
        context_text: str,
        iteration: int = 1,
    ) -> dict:
        """Run review and return structured result dict.

        Builds a context object with ``project_id``, ``sprint_number``,
        ``iteration``, and ``content``, then calls ``execute()``.
        When ``workspace_manager`` is wired, the result is also persisted
        to the sprint-scoped ArtifactStore.

        Returns the structured dict
        (``{"approved": bool, "violations": [...], ...}``).
        """
        from types import SimpleNamespace
        ctx = SimpleNamespace(
            project_id=project_id,
            sprint_number=sprint_number,
            iteration=iteration,
            content=context_text,
        )
        artifact = self.execute(ctx)

        # Persist to sprint-scoped ArtifactStore when workspace_manager is wired.
        if self._workspace_manager is not None:
            try:
                store = self._workspace_manager.get_artifact_store(project_id)
                store.write(
                    scope=f"sprint_{sprint_number}",
                    name="tech_review",
                    data={
                        "content": artifact.content,
                        "structured": artifact.structured_content or {},
                        "stage": "TechLead",
                        "written_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[TechLeadAgent] non-fatal ArtifactStore write failure: %s", exc
                )

        return artifact.structured_content or {
            "approved": False, "violations": [], "iteration": iteration
        }

"""BugAnalystAgent — QA findings root-cause classifier.

Runs when QA finds failures in a sprint.  Reads QA findings, user stories,
architecture, and file plan, then classifies each failure into one of:

    code_bug | spec_bug | architecture_bug | security_violation

and identifies which agent should fix it.  Output structure::

    {
      "type": "code_bug | spec_bug | architecture_bug | security_violation",
      "root_artifact": "user_stories | architecture | backend code | security_rules",
      "affected_agent": "Backend | Frontend | ProductOwner | Architect",
      "fix_instruction": "<specific instruction for the affected agent>",
      "sprint": N,
      "iteration": N
    }

Output is written to::

    artifacts/sprint_{N}/bug_analysis.json

via :class:`~app.workspace.artifact_store.ArtifactStore`.

The SprintSupervisor (Phase 3) reads this output and routes the fix
instruction to the right agent.
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
You are a Senior QA Lead performing root-cause analysis on test failures.

You receive:
- QA findings: what tests failed and why.
- User stories: the spec that should have been implemented.
- Architecture: the design the code was supposed to follow.
- File plan: what files were supposed to be built this sprint.

Your job is to classify EACH failure and output a single JSON object describing
the most critical root cause (if multiple bugs exist, pick the blocking one):

{
  "type": "code_bug | spec_bug | architecture_bug | security_violation",
  "root_artifact": "backend code | frontend code | user_stories | architecture | security_rules",
  "affected_agent": "Backend | Frontend | ProductOwner | Architect | Security",
  "fix_instruction": "<specific, actionable instruction for the affected agent>",
  "failures_analysed": <integer — how many distinct failures were found>,
  "sprint": <sprint number integer>,
  "iteration": <analysis iteration integer, starting at 1>
}

Classification rules:
- code_bug: the spec and design are correct but the implementation is wrong.
  root_artifact = the file or module that is broken.
  affected_agent = Backend or Frontend depending on file.
- spec_bug: the user story is ambiguous, missing, or contradicts the failure.
  root_artifact = "user_stories".
  affected_agent = ProductOwner.
- architecture_bug: the design decision caused the failure (wrong tech, missing layer).
  root_artifact = "architecture".
  affected_agent = Architect.
- security_violation: a security rule was violated (hardcoded secret, missing auth, SQL injection).
  root_artifact = "security_rules".
  affected_agent = Backend or Frontend.

The fix_instruction must be specific enough that the affected agent can act on it
without re-reading this analysis. Include file paths, function names, or story IDs
where relevant.

Output ONLY the JSON object — no markdown, no explanation outside it.
"""


# ---------------------------------------------------------------------------
# Primary action
# ---------------------------------------------------------------------------

class _BugAnalysisAction(BaseAction):
    """Send QA findings + context to the LLM for root-cause classification."""

    name = "BugAnalysis"
    description = "Classify QA failures into root causes and route to the right agent."

    def run(self, context: object, llm: object) -> ActionOutput:  # type: ignore[override]
        content = getattr(context, "content", str(context)) if context is not None else ""
        sprint = getattr(context, "sprint_number", 0)
        iteration = getattr(context, "iteration", 1)

        prompt = (
            f"=== BUG ANALYSIS REQUEST — Sprint {sprint}, Iteration {iteration} ===\n\n"
            f"{content}\n\n"
            "Classify the root cause and output your analysis as a JSON object."
        )

        response = llm.generate_text(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            stage="BugAnalyst",
            agent="BugAnalystAgent",
        )
        structured = self.extract_json(response.content)

        # Stamp required fields if LLM omitted them.
        if "type" not in structured:
            structured["type"] = "code_bug"
        if "affected_agent" not in structured:
            structured["affected_agent"] = "Backend"
        if "fix_instruction" not in structured:
            structured["fix_instruction"] = "See qa_findings for details."
        structured.setdefault("sprint", sprint)
        structured.setdefault("iteration", iteration)
        structured.setdefault("root_artifact", "backend code")
        structured.setdefault("failures_analysed", 1)

        return ActionOutput(content=response.content, structured=structured)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class BugAnalystAgent(BaseAgent):
    """Root-cause analyst agent — classifies QA failures and routes fixes.

    Reads QA findings (and optionally user stories, architecture, and file
    plan from the context) and produces a structured classification that
    SprintSupervisor uses to route the fix to the right agent.

    Parameters
    ----------
    workspace_manager:
        Injected so the agent can write to ArtifactStore.  ``None`` in
        unit-test paths where the write is skipped.
    llm_manager:
        The LLM provider.  Defaults to ``LLMManager()`` if not injected.
    primary_action:
        Overrides the default :class:`_BugAnalysisAction` (useful in tests).
    """

    artifact_name = "bug_analysis"

    def __init__(
        self,
        workspace_manager=None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return _BugAnalysisAction()

    def analyse(
        self,
        project_id: str,
        sprint_number: int,
        qa_findings: str,
        user_stories: str = "",
        architecture: str = "",
        file_plan: str = "",
        iteration: int = 1,
    ) -> dict:
        """Build context from named inputs, run analysis, and return a plain dict.

        When ``workspace_manager`` is wired, the result is also persisted
        to the sprint-scoped ArtifactStore.
        """
        from types import SimpleNamespace

        parts = [f"QA FINDINGS:\n{qa_findings}"]
        if user_stories:
            parts.append(f"USER STORIES:\n{user_stories}")
        if architecture:
            parts.append(f"ARCHITECTURE:\n{architecture}")
        if file_plan:
            parts.append(f"FILE PLAN:\n{file_plan}")

        ctx = SimpleNamespace(
            project_id=project_id,
            sprint_number=sprint_number,
            iteration=iteration,
            content="\n\n".join(parts),
        )
        artifact = self.execute(ctx)

        # Persist to sprint-scoped ArtifactStore when workspace_manager is wired.
        if self._workspace_manager is not None:
            try:
                store = self._workspace_manager.get_artifact_store(project_id)
                store.write(
                    scope=f"sprint_{sprint_number}",
                    name="bug_analysis",
                    data={
                        "content": artifact.content,
                        "structured": artifact.structured_content or {},
                        "stage": "BugAnalyst",
                        "written_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[BugAnalystAgent] non-fatal ArtifactStore write failure: %s", exc
                )

        return artifact.structured_content or {
            "type": "code_bug",
            "affected_agent": "Backend",
            "fix_instruction": "See qa_findings for details.",
            "sprint": sprint_number,
            "iteration": iteration,
        }

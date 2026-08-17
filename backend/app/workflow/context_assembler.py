"""ContextAssembler — single responsibility: build the full prompt context for a stage.

Consolidates every enrichment that previously lived in WorkflowEngine._with_*()
methods and the MemoryOrchestrator path.  Exposes one public method:

    assemble(project_id, stage_name, caller_context) -> str

The caller_context parameter carries sprint-specific content (goal, features,
ScrumMaster plan, SprintMonitor brief) that would otherwise be silently
discarded by MemoryOrchestrator overwriting the content string.

Per-stage context budgets
-------------------------
Every call to :meth:`_assemble_legacy` (and the fallback path inside
:meth:`_assemble_via_orchestrator`) fetches a :class:`ContextBudget` from
:class:`ContextBudgetRegistry` at the start of assembly.  Each enrichment is
only called when its corresponding budget flag is ``True``.  When the
``"default"`` budget applies (unknown stage), all flags are ``True`` and
behaviour is identical to the original unconditional enrichment — no regression.

The active budget is stored on ``self._current_budget`` for the duration of
the assembly call so that enrichment helpers can read size limits (e.g.
``predecessor_max_chars``, ``lessons_limit``) without requiring signature
changes.  This attribute must be treated as a call-scoped temporary; it is
overwritten at the start of each :meth:`_assemble_legacy` invocation.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ..shared.constants import (
    DESIGN_DEPENDENT_STAGES,
    DESIGN_MEMORY_KEY,
    GATE_FEEDBACK_MAP,
    WORKFLOW_MESSAGE_KEY,
)
from ..shared.enums.stage import Stage
from .context_budget import ContextBudget, ContextBudgetRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssembleResult:
    """Return value of :meth:`ContextAssembler.assemble`.

    Carries the assembled prompt-context string, a flag indicating whether
    TemplateEngine injected a structural template hint into the context,
    the exact injected_template_id (if injected), and the similarity score (if any).
    """

    context: str
    template_injected: bool = False
    injected_template_id: str | None = None
    template_similarity_score: float | None = None



class ContextAssembler:
    """Assembles the complete prompt context for a single stage execution.

    Parameters
    ----------
    memory_orchestrator:
        High-level context assembler covering all four memory layers.
        When present, used as the primary context source; caller_context
        is merged in as an additional field rather than discarded.
    memory_manager:
        Low-level key/value store.  Used for the legacy enrichment path
        and for gate-feedback / predecessor-message reads.
    artifact_manager:
        Reads persisted stage artifacts.
    workspace_manager:
        Reads project.json (original_request, etc.).
    learning_loop:
        Provides semantically relevant past patterns.
    lesson_store:
        Provides human-readable lessons for this stage/project.
    context_orchestrator:
        Layer 4 procedural intelligence (file index, dependency graph).
    template_engine:
        Injects structural templates from similar past approvals.
    """

    def __init__(
        self,
        memory_orchestrator: Any = None,
        memory_manager: Any = None,
        artifact_manager: Any = None,
        workspace_manager: Any = None,
        learning_loop: Any = None,
        lesson_store: Any = None,
        context_orchestrator: Any = None,
        template_engine: Any = None,
    ) -> None:
        self._memory_orchestrator = memory_orchestrator
        self._memory_manager = memory_manager
        self._artifact_manager = artifact_manager
        self._workspace_manager = workspace_manager
        self._learning_loop = learning_loop
        self._lesson_store = lesson_store
        self._context_orchestrator = context_orchestrator
        self._template_engine = template_engine
        # Call-scoped budget.  Set at the start of each _assemble_legacy /
        # _assemble_via_orchestrator call; read by enrichment helpers for size
        # limits.  None before the first assembly call.
        self._current_budget: ContextBudget | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(
        self,
        project_id: str,
        stage_name: str,
        caller_context: str = "",
    ) -> AssembleResult:
        """Build the full prompt context string for stage_name.

        Parameters
        ----------
        project_id:
            Project being built.
        stage_name:
            Canonical stage name (e.g. "Architect", "BackendDeveloper").
        caller_context:
            Sprint-specific or ad-hoc content provided by the caller
            (e.g. sprint goal + architecture + ScrumMaster plan assembled
            by SprintExecutor).  Merged into the memory-orchestrator context
            rather than discarded.

        Returns
        -------
        AssembleResult
            .context            — assembled prompt string ready for StageRunner
            .template_injected  — True if TemplateEngine injected a structural hint
        """
        try:
            stage = Stage(stage_name)
        except ValueError:
            stage = None

        # context_hint is the richer ctx_dict from the orchestrator path.
        # It is used as the similarity context for TemplateEngine.find_similar()
        # so that key-set Jaccard operates on meaningful stage-input keys rather
        # than just {"project_id", "stage"}.  The legacy path has no equivalent
        # structured dict, so context_hint stays None there.
        context_hint: dict | None = None

        if self._memory_orchestrator is not None and stage is not None:
            base, context_hint = self._assemble_via_orchestrator(
                project_id, stage, stage_name, caller_context,
            )
        else:
            base = self._assemble_legacy(project_id, stage_name, caller_context)

        # Post-enrichments applied regardless of path ---
        base = self._inject_gate_feedback(project_id, stage_name, base)
        base = self._inject_sandbox_results(project_id, stage_name, base)
        base, template_injected, injected_template_id, template_similarity_score = self._inject_template(
            stage_name, project_id, base, context_hint=context_hint,
        )

        # Enforce per-stage token budget from ContextBudgetRegistry
        budget = ContextBudgetRegistry.get(stage_name)
        if budget.max_total_tokens > 0:
            max_chars = budget.max_total_tokens * 4
            if len(base) > max_chars:
                trimmed = base[:max_chars]
                logger.warning(
                    "ContextAssembler: assembled context exceeds stage budget — "
                    "trimmed from %d to %d chars (stage=%s max_tokens=%d)",
                    len(base), max_chars, stage_name, budget.max_total_tokens,
                )
                base = trimmed

        return AssembleResult(
            context=base,
            template_injected=template_injected,
            injected_template_id=injected_template_id,
            template_similarity_score=template_similarity_score,
        )


    # ------------------------------------------------------------------
    # New path: MemoryOrchestrator
    # ------------------------------------------------------------------

    def _assemble_via_orchestrator(
        self,
        project_id: str,
        stage: Stage,
        stage_name: str,
        caller_context: str,
    ) -> tuple[str, dict]:
        """Assemble context via MemoryOrchestrator, gated by the stage budget.

        The budget is fetched and stored in ``self._current_budget`` so that
        the fallback leg (which calls :meth:`_assemble_legacy`) inherits the
        correct limits.  On the primary leg the ``ctx_dict`` returned by the
        orchestrator is pruned of enrichment categories that the budget
        disables — a best-effort filter using canonical key names.

        Returns
        -------
        tuple[str, dict]
            The serialized context string and the raw ``ctx_dict`` used to build
            it.  The dict is returned so callers can pass it to
            :meth:`_inject_template` as a richer similarity context for
            TemplateEngine — avoiding a second ``get_context()`` call.

            On failure, falls back to the legacy path and returns an empty dict
            as the hint (legacy path has no structured context object).
        """
        # Store budget so the fallback path and enrichment helpers can read it.
        budget = ContextBudgetRegistry.get(stage_name)
        self._current_budget = budget

        try:
            stage_ctx = self._memory_orchestrator.get_context(project_id, stage)
            ctx_dict = stage_ctx.to_prompt_dict()

            # ── Budget enforcement on orchestrator output ──────────────────
            # The orchestrator builds its own rich context.  We prune keys that
            # the budget disables so irrelevant data never reaches the LLM.
            # Key names are canonical guesses; unknown keys pass through safely.
            if not budget.include_lessons:
                for _k in ("lessons", "lessons_learned", "lesson_store"):
                    ctx_dict.pop(_k, None)

            if not budget.include_patterns:
                for _k in ("past_patterns", "patterns", "relevant_patterns"):
                    ctx_dict.pop(_k, None)

            if not budget.include_intelligence:
                for _k in (
                    "relevant_files", "dependency_context", "project_overview",
                    "file_context", "intelligence", "code_summaries",
                ):
                    ctx_dict.pop(_k, None)

            if not budget.include_clarification:
                for _k in ("clarification", "clarification_context", "clarification_artifact"):
                    ctx_dict.pop(_k, None)

            if not budget.include_design:
                for _k in ("design", "design_spec", "design_artifact", "approved_design"):
                    ctx_dict.pop(_k, None)

            # Merge caller_context so sprint-assembled content is not discarded.
            if caller_context:
                ctx_dict["caller_context"] = caller_context

            raw_bp = None
            if self._memory_manager is not None and stage_name not in {
                "Architect", "architect", "Clarification", "clarification",
                "ProductOwner", "product_owner", "StrategicReview", "strategic_review",
            }:
                try:
                    raw_bp = self._memory_manager.load(project_id, "blueprint:latest")
                    if raw_bp:
                        bp_data = json.loads(raw_bp) if isinstance(raw_bp, str) else raw_bp
                        ctx_dict["project_blueprint"] = {
                            k: bp_data[k]
                            for k in ("project_type", "folder_structure", "dependencies", "entry_points", "constraints")
                            if k in bp_data
                        }
                except Exception as exc:
                    logger.debug("blueprint inject into orchestrator ctx failed: %s", exc)

            return json.dumps(ctx_dict, indent=2), ctx_dict
        except Exception as exc:
            logger.warning(
                "ContextAssembler: MemoryOrchestrator failed for %s/%s, falling back: %s",
                project_id, stage_name, exc,
            )
            return self._assemble_legacy(project_id, stage_name, caller_context), {}

    # ------------------------------------------------------------------
    # Legacy path: six ad-hoc enrichment calls, gated by ContextBudget
    # ------------------------------------------------------------------

    def _assemble_legacy(
        self,
        project_id: str,
        stage_name: str,
        caller_context: str,
    ) -> str:
        """Assemble context via individual enrichment helpers.

        The stage budget is fetched first and stored as ``self._current_budget``
        so enrichment helpers can access size limits without signature changes.
        Each enrichment is only called when its corresponding budget flag is
        ``True``.  When the ``"default"`` budget applies, every flag is ``True``
        and the call sequence is identical to the previous implementation —
        zero regression.

        If ``self._current_budget`` was already set (e.g. by
        :meth:`_assemble_via_orchestrator` before falling back here), the
        budget is reused rather than looked up again so that the budget is
        consistent across the whole assembly.
        """
        if self._current_budget is None:
            self._current_budget = ContextBudgetRegistry.get(stage_name)
        budget = self._current_budget

        base = caller_context

        base = self._with_blueprint(project_id, stage_name, base)

        if budget.include_predecessor:
            base = self._with_predecessor_message(project_id, base)

        if budget.include_clarification:
            base = self._with_clarification_context(project_id, stage_name, base)

        if budget.include_patterns:
            base = self._with_relevant_patterns(base, stage_name, caller_context, project_id)

        if budget.include_design:
            base = self._with_design_context(project_id, stage_name, base)

        if budget.include_lessons:
            base = self._with_lessons(base, stage_name, project_id)

        if budget.include_intelligence:
            base = self._with_intelligence_context(project_id, stage_name, base)

        return base

    # ------------------------------------------------------------------
    # Enrichment helpers (previously WorkflowEngine._with_*())
    # Do NOT change the signatures of these methods.
    # ------------------------------------------------------------------

    def _with_blueprint(self, project_id: str, stage_name: str, content: str) -> str:
        """Inject the project blueprint into the agent's context.

        The blueprint is the authoritative source for folder structure, dependency
        versions, entry points, and constraints. Injected for all stages except
        Architect itself (which produces the blueprint, not consumes it) and
        Clarification/ProductOwner (which run before the blueprint exists).

        Skipped silently if no blueprint exists in memory.
        """
        _SKIP_STAGES = {
            "Architect", "architect", "Clarification", "clarification",
            "ProductOwner", "product_owner", "StrategicReview", "strategic_review",
        }
        if stage_name in _SKIP_STAGES:
            return content
        if self._memory_manager is None:
            return content
        try:
            raw = self._memory_manager.load(project_id, "blueprint:latest")
            if not raw:
                return content
            data = json.loads(raw) if isinstance(raw, str) else raw
            # Extract only the blueprint-relevant fields to keep context compact
            blueprint_summary = {
                k: data[k]
                for k in ("project_type", "folder_structure", "dependencies",
                          "entry_points", "constraints")
                if k in data
            }
            if not blueprint_summary:
                return content
            blueprint_text = json.dumps(blueprint_summary, indent=2)
            header = (
                "### Project Blueprint (authoritative — follow exactly)\n"
                "Folder structure, dependency versions, entry points, and constraints "
                "below are decided by the Architect. Do not deviate.\n\n"
                f"```json\n{blueprint_text}\n```"
            )
            return f"{header}\n\n{content}"
        except Exception as exc:
            logger.debug("_with_blueprint skipped: %s", exc)
        return content

    def _with_predecessor_message(self, project_id: str, content: str) -> str:
        """Inject the most-recently-approved stage's message.

        Truncation
        ----------
        When the active budget has ``predecessor_max_chars > 0``, the message
        body is trimmed to that limit and a ``...[truncated]`` marker is appended.
        This prevents a single long predecessor from crowding out other enrichments.
        The budget is read from ``self._current_budget``; callers must set it before
        invoking this helper (which :meth:`_assemble_legacy` and
        :meth:`_assemble_via_orchestrator` guarantee).
        """
        if self._memory_manager is None:
            return content
        try:
            from ..shared.schemas.message import AgentMessage
            raw = self._memory_manager.load(project_id, WORKFLOW_MESSAGE_KEY)
            if not raw:
                return content
            msg = AgentMessage.model_validate_json(raw)

            msg_content: str = msg.content

            # Apply predecessor_max_chars from the active budget.
            budget = self._current_budget
            if budget is not None and budget.predecessor_max_chars > 0:
                if len(msg_content) > budget.predecessor_max_chars:
                    msg_content = msg_content[: budget.predecessor_max_chars] + "...[truncated]"
                    logger.debug(
                        "_with_predecessor_message: truncated to %d chars for stage budget",
                        budget.predecessor_max_chars,
                    )

            return f"{content}\n\n### Previous Stage Output ({msg.role})\n{msg_content}"
        except Exception as exc:
            logger.debug("_with_predecessor_message skipped: %s", exc)
        return content

    def _with_clarification_context(
        self, project_id: str, stage_name: str, content: str,
    ) -> str:
        if stage_name not in (Stage.ProductOwner.value, "ProductOwner", "product_owner"):
            return content
        if self._artifact_manager is None:
            return content
        try:
            clar_art = self._artifact_manager.get_artifact(project_id, Stage.Clarification)
            if clar_art is None:
                p_data = (self._workspace_manager.load_project_json(project_id) or {}
                          if self._workspace_manager else {})
                orig = p_data.get("original_request") or p_data.get("description") or content
                clarification_struct: dict = {
                    "original_request": orig,
                    "project_description": orig,
                    "functional_requirements": [],
                    "non_functional_requirements": [],
                    "scale_profile": {"user_count": "unknown"},
                    "inferred_scope": (
                        "No clarification performed. "
                        "Infer scope from original_request."
                    ),
                }
                logger.warning(
                    "_with_clarification_context: no Clarification artifact for %s — fallback",
                    project_id,
                )
            else:
                clarification_struct = getattr(clar_art, "structured_content", None) or {}

            domain_art = self._artifact_manager.get_artifact(project_id, Stage.DomainResearch)
            domain_struct = (
                getattr(domain_art, "structured_content", None) or {}
                if domain_art else {}
            )
            strategic_art = self._artifact_manager.get_artifact(
                project_id, Stage.StrategicReview,
            )
            strategic_struct = (
                getattr(strategic_art, "structured_content", None) or {}
                if strategic_art else {}
            )

            split_pat = re.compile(r"\n\n###\s+Previous Stage Output[^\n]*\n", re.IGNORECASE)
            parts = split_pat.split(content, maxsplit=1)
            original_request = parts[0].strip() if parts else content.strip()

            return json.dumps({
                "original_request": original_request,
                "clarification": clarification_struct,
                "strategic_brief": strategic_struct,
                "domain_research": domain_struct,
            }, indent=2)
        except Exception as exc:
            logger.debug("_with_clarification_context skipped: %s", exc)
        return content

    def _with_relevant_patterns(
        self,
        content: str,
        stage_name: str,
        task: str,
        project_id: str,
    ) -> str:
        """Inject semantically-relevant past patterns from LearningLoop.

        The number of patterns is capped by ``self._current_budget.patterns_limit``
        when a budget is active.  The LearningLoop is called without a limit
        argument (its signature is unchanged); the result list is sliced here.
        """
        if self._learning_loop is None:
            return content
        try:
            patterns = self._learning_loop.get_relevant_patterns(
                task, stage_name, project_id=project_id,
            )
            # Apply budget patterns_limit — slice BEFORE formatting so the
            # LearningLoop is not invoked more times than necessary.
            budget = self._current_budget
            if budget is not None and budget.patterns_limit > 0 and patterns:
                patterns = patterns[: budget.patterns_limit]

            if patterns:
                patterns_text = "\n".join(f"- {p}" for p in patterns)
                return f"{content}\n\n### Relevant Past Patterns\n{patterns_text}"
        except Exception as exc:
            logger.debug("_with_relevant_patterns skipped: %s", exc)
        return content

    def _with_design_context(
        self, project_id: str, stage_name: str, content: str,
    ) -> str:
        if stage_name not in DESIGN_DEPENDENT_STAGES:
            return content
        if self._memory_manager is None:
            return content
        try:
            design_entry = self._memory_manager.load(project_id, DESIGN_MEMORY_KEY)
            if design_entry:
                return f"{content}\n\n### Approved Design Spec\n{design_entry}"
        except Exception as exc:
            logger.debug("_with_design_context skipped: %s", exc)
        return content

    def _with_lessons(self, content: str, stage_name: str, project_id: str) -> str:
        """Inject human-readable lessons from LessonStore.

        The number of lessons requested is driven by
        ``self._current_budget.lessons_limit`` when a budget is active,
        otherwise falls back to the previous hard-coded value of ``3``.
        """
        if self._lesson_store is None:
            return content
        try:
            budget = self._current_budget
            limit = budget.lessons_limit if budget is not None else 3

            lessons = self._lesson_store.get_lessons(
                stage=stage_name, project_id=project_id, limit=limit,
            )
            if not lessons:
                return content
            lines = [f"### Lessons Learned for {stage_name} (this project)"]
            for lesson in lessons:
                lines.append(f"- What worked: {lesson.what_worked[:200]}")
                if lesson.what_failed:
                    lines.append(f"  What failed: {lesson.what_failed[:150]}")
                if lesson.reviewer_said:
                    lines.append(f"  Reviewer said: {lesson.reviewer_said[:150]}")
            return f"{content}\n\n" + "\n".join(lines)
        except Exception as exc:
            logger.debug("_with_lessons skipped: %s", exc)
        return content

    def _with_intelligence_context(
        self, project_id: str, stage_name: str, content: str,
    ) -> str:
        if self._context_orchestrator is None:
            return content
        try:
            package = self._context_orchestrator.build(
                project_id=project_id,
                stage=stage_name,
                task_description=content[:200],
            )
            prefix = self._context_orchestrator.format_as_prompt_section(package)
            if prefix:
                return f"{prefix}\n\n━━━ YOUR TASK ━━━\n{content}"
        except Exception as exc:
            logger.debug("_with_intelligence_context skipped: %s", exc)
        return content

    # ------------------------------------------------------------------
    # Post-enrichments (applied on both paths)
    # ------------------------------------------------------------------

    def _inject_gate_feedback(
        self, project_id: str, stage_name: str, content: str,
    ) -> str:
        gate = GATE_FEEDBACK_MAP.get(stage_name)
        if not gate or self._memory_manager is None:
            return content
        try:
            feedback = self._memory_manager.load(project_id, f"gate:feedback:{gate}")
            if feedback:
                logger.info(
                    "gate feedback injected: project=%s stage=%s gate=%s",
                    project_id, stage_name, gate,
                )
                return (
                    f"{content}\n\n"
                    f"--- HUMAN GATE FEEDBACK ---\n"
                    f"A human reviewer requested the following revision at the {gate} gate:\n"
                    f"{feedback}\n"
                    f"You MUST incorporate all of this feedback in your response.\n"
                    f"--- END GATE FEEDBACK ---"
                )
        except Exception as exc:
            logger.debug("_inject_gate_feedback skipped: %s", exc)
        return content

    def _inject_sandbox_results(
        self, project_id: str, stage_name: str, content: str,
    ) -> str:
        if stage_name != Stage.BugAnalyst.value or self._memory_manager is None:
            return content
        try:
            sandbox_json = self._memory_manager.load(project_id, "sandbox:latest")
            if not sandbox_json:
                return content
            data = (
                json.loads(sandbox_json) if isinstance(sandbox_json, str) else sandbox_json
            )
            lint_count = data.get("lint", {}).get("error_count", 0)
            build_ok = data.get("build", {}).get("success", True)
            test_passed = data.get("test", {}).get("passed", 0)
            test_total = data.get("test", {}).get("total", 0)
            lint_errors = data.get("lint", {}).get("errors", [])
            lint_lines = "\n".join(
                f"  - {e.get('file','?')}:{e.get('line',0)}: {e.get('message','')}"
                for e in lint_errors[:20]
            )
            build_errors = data.get("build", {}).get("errors", [])
            build_lines = "\n".join(f"  - {e}" for e in build_errors[:10])
            return (
                f"## AUTOMATED VERIFICATION RESULTS\n"
                f"- Lint errors: {lint_count}\n"
                f"- Build: {'PASSED' if build_ok else 'FAILED'}\n"
                f"- Tests: {test_passed}/{test_total} passed\n\n"
                + (f"Lint issues:\n{lint_lines}\n\n" if lint_lines else "")
                + (f"Build errors:\n{build_lines}\n\n" if build_lines else "")
                + f"Address all automated issues above.\n\n---\n\n{content}"
            )
        except Exception as exc:
            logger.debug("_inject_sandbox_results skipped: %s", exc)
        return content

    def _inject_template(
        self,
        stage_name: str,
        project_id: str,
        content: str,
        context_hint: dict | None = None,
    ) -> tuple[str, bool, str | None, float | None]:
        """Attempt to inject a structural template hint into content.

        Parameters
        ----------
        stage_name:
            Stage being assembled (used to filter templates by stage).
        project_id:
            Current project identifier (included in the fallback context dict).
        content:
            The assembled context string so far.
        context_hint:
            Optional richer context dict (e.g. ``ctx_dict`` from
            ``_assemble_via_orchestrator``) used as the similarity context for
            :meth:`TemplateEngine.find_similar`.  When provided, key-set Jaccard
            is computed against this dict's flattened keys, producing more
            meaningful similarity scores than the two-key fallback.
            When None or absent (legacy path), falls back to
            ``{"project_id": ..., "stage": ...}``.

        Returns
        -------
        tuple[str, bool, str | None, float | None]
            (augmented_content, template_injected, injected_template_id, template_similarity_score)
            ``template_injected`` is True only when a template was found and
            successfully appended; False in all other cases including when no
            template engine is wired, no templates exist, or an exception occurs.
        """
        if self._template_engine is None:
            return content, False, None, None
        try:
            # Use the richer context_hint when available; fall back to the
            # minimal two-key dict so the legacy path still works.
            similarity_context: dict = context_hint if context_hint else {
                "project_id": project_id,
                "stage": stage_name,
            }
            similar = self._template_engine.find_similar(
                stage_name, similarity_context, limit=1,
            )
            if not similar:
                return content, False, None, None
            tpl = similar[0]
            injected = self._template_engine.inject_template(tpl, similarity_context)
            if injected:
                augmented = (
                    f"{content}\n\n"
                    f"### STRUCTURAL TEMPLATE (from a similar past project)\n"
                    f"Use this structure as a starting point:\n"
                    f"{json.dumps(injected, indent=2)}"
                )
                logger.info(
                    "_inject_template: injected template_id=%s for stage=%s project=%s",
                    tpl.template_id, stage_name, project_id,
                )
                return augmented, True, tpl.template_id, None
        except Exception as exc:
            logger.debug("_inject_template skipped: %s", exc)
        return content, False, None, None

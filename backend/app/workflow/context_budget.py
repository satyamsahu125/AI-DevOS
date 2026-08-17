"""Per-stage context budgets for :class:`~app.workflow.context_assembler.ContextAssembler`.

:class:`ContextBudget` is a frozen dataclass that declares, per stage, which
enrichments the assembler is allowed to call and how large each enrichment
is permitted to be.

:class:`ContextBudgetRegistry` is a pure class — no instance is ever needed.
Its :meth:`ContextBudgetRegistry.get` class-method normalises any stage name
variant (``"BackendDeveloper"``, ``"backend"``, ``"BACKEND"`` …) and returns
the matching :class:`ContextBudget`, falling back to ``"default"`` for unknown
stages.

Design invariants
-----------------
* **Additive**: if every flag is ``True``, behaviour is identical to the
  previous unconditional enrichment (that is the ``"default"`` budget).
* **Zero-regression**: stages not listed in the registry receive the
  ``"default"`` budget, which mirrors the unbounded original behaviour.
* **Immutable**: :class:`ContextBudget` is ``frozen=True`` — no field is ever
  mutated after construction.
* **Zero instance state**: :class:`ContextBudgetRegistry` carries only
  class-level attributes; nothing in it varies at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    """Declares which enrichments a stage may receive and their size limits.

    Parameters
    ----------
    max_total_tokens:
        Soft upper bound for the assembled context string (in LLM tokens,
        assuming ≈4 chars/token).  Reserved for future enforcement inside
        :class:`~app.workflow.context_assembler.ContextAssembler` — not
        actively trimmed today.
    include_predecessor:
        Inject the most-recently-approved stage's message as a
        "Previous Stage Output" section.
    predecessor_max_chars:
        Maximum characters retained from the predecessor message before
        appending ``...[truncated]``.  Ignored when
        ``include_predecessor=False``.  A value of ``0`` means no limit.
    include_lessons:
        Inject human-readable lessons from :class:`~app.memory.lesson_store.LessonStore`.
    lessons_limit:
        Maximum number of lessons to inject.  Maps to the ``limit`` argument
        of :meth:`~app.memory.lesson_store.LessonStore.get_lessons`.
    include_patterns:
        Inject semantically-relevant past patterns from
        :class:`~app.memory.learning_loop.LearningLoop`.
    patterns_limit:
        Maximum number of patterns to retain from the LearningLoop response.
    include_design:
        Inject the approved design artifact (``DESIGN_MEMORY_KEY`` slot in
        :class:`~app.memory.manager.MemoryManager`).
    include_intelligence:
        Inject file-level intelligence from
        :class:`~app.intelligence.context_orchestrator.ContextOrchestrator`
        (file summaries, dependency graph, relevant existing files).
    include_clarification:
        Inject the :class:`~app.shared.enums.stage.Stage.Clarification`
        artifact plus DomainResearch and StrategicReview.  Only
        ``ProductOwner`` benefits from this; all later stages receive the
        structured output that ProductOwner already produced.
    """

    max_total_tokens: int
    include_predecessor: bool
    predecessor_max_chars: int
    include_lessons: bool
    lessons_limit: int
    include_patterns: bool
    patterns_limit: int
    include_design: bool
    include_intelligence: bool
    include_clarification: bool


class ContextBudgetRegistry:
    """Pure class mapping stage names to their :class:`ContextBudget`.

    All state is class-level and frozen — no instance is ever created.
    Call :meth:`get` directly on the class::

        budget = ContextBudgetRegistry.get("BackendDeveloper")

    Stage name normalisation
    ------------------------
    Stage names arrive in several formats (``"BackendDeveloper"``,
    ``"backend"``, ``"QA"`` …).  :meth:`get` lowercases the name and consults
    :attr:`_CANONICAL` before looking up :attr:`_BUDGETS`.  Unknown stages fall
    through to the ``"default"`` budget, which enables every enrichment flag
    and is therefore byte-for-byte equivalent to the previous unconditional
    enrichment behaviour.
    """

    # ------------------------------------------------------------------
    # Named budget definitions — one entry per logical stage group
    # ------------------------------------------------------------------

    _BUDGETS: dict[str, ContextBudget] = {
        # ── Clarification ────────────────────────────────────────────
        # Starts from scratch.  No predecessor (it IS the first stage),
        # no lessons (nothing recorded yet for this project), no patterns,
        # no design, no intelligence, no clarification artifact (it produces one).
        "clarification": ContextBudget(
            max_total_tokens=2_000,
            include_predecessor=False,
            predecessor_max_chars=0,
            include_lessons=False,
            lessons_limit=0,
            include_patterns=False,
            patterns_limit=0,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── ProductOwner ─────────────────────────────────────────────
        # Needs the Clarification artifact to expand requirements.
        # Does NOT need design (not produced yet) or intelligence (no code yet).
        "product_owner": ContextBudget(
            max_total_tokens=6_000,
            include_predecessor=True,
            predecessor_max_chars=2_000,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=True,
            patterns_limit=3,
            include_design=False,
            include_intelligence=False,
            include_clarification=True,
        ),

        # ── Architect ────────────────────────────────────────────────
        # Needs predecessor (ProductOwner output), lessons, and patterns to
        # shape the architecture.  Does NOT need design (it produces design)
        # or intelligence (no code exists yet at architecture time).
        "architect": ContextBudget(
            max_total_tokens=8_000,
            include_predecessor=True,
            predecessor_max_chars=3_000,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=True,
            patterns_limit=3,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── Designer ─────────────────────────────────────────────────
        # Needs predecessor (Architect output) and lessons.  No patterns
        # (patterns are architecture-level, not UI-level), no design (it
        # produces the design artifact), no intelligence (no code yet).
        "designer": ContextBudget(
            max_total_tokens=6_000,
            include_predecessor=True,
            predecessor_max_chars=2_000,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=False,
            patterns_limit=0,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── BackendDeveloper ─────────────────────────────────────────
        # Needs the approved design spec plus file-level intelligence
        # (existing files to avoid duplication, dependency graph for imports).
        # Predecessor increased to 6000 to accommodate Architect artifact
        # (typically 5,000–10,000 chars) without truncation.
        "backend": ContextBudget(
            max_total_tokens=12_000,
            include_predecessor=True,
            predecessor_max_chars=6_000,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=True,
            patterns_limit=2,
            include_design=True,
            include_intelligence=True,
            include_clarification=False,
        ),

        # ── FrontendDeveloper ────────────────────────────────────────
        # Same as BackendDeveloper — design spec drives component structure,
        # intelligence prevents re-generating existing components.
        "frontend": ContextBudget(
            max_total_tokens=12_000,
            include_predecessor=True,
            predecessor_max_chars=6_000,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=True,
            patterns_limit=2,
            include_design=True,
            include_intelligence=True,
            include_clarification=False,
        ),

        # ── QA ───────────────────────────────────────────────────────
        # QA writes test scenarios and acceptance criteria — it does NOT need
        # file-level intelligence (which can be 20K+ tokens for large projects
        # and pushes the full prompt past the model's context window).
        # Predecessor is kept very short; the sprint plan and ProductOwner
        # artifact captured via the stage-artifact mechanism are sufficient.
        # Patterns are not useful here — QA strategy is project-specific.
        "qa": ContextBudget(
            max_total_tokens=6_000,
            include_predecessor=True,
            predecessor_max_chars=500,
            include_lessons=True,
            lessons_limit=2,
            include_patterns=False,
            patterns_limit=0,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── DevOps ───────────────────────────────────────────────────
        # Lightweight: only predecessor (architect/file-planner output) and a
        # single lesson.  Infrastructure decisions rarely benefit from past
        # patterns or design context.
        "devops": ContextBudget(
            max_total_tokens=6_000,
            include_predecessor=True,
            predecessor_max_chars=1_000,
            include_lessons=True,
            lessons_limit=1,
            include_patterns=False,
            patterns_limit=0,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── Document ─────────────────────────────────────────────────
        # Same profile as DevOps — reads predecessor for the artifact
        # to document, one lesson for style guidance.
        "document": ContextBudget(
            max_total_tokens=6_000,
            include_predecessor=True,
            predecessor_max_chars=1_000,
            include_lessons=True,
            lessons_limit=1,
            include_patterns=False,
            patterns_limit=0,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),

        # ── Default ──────────────────────────────────────────────────
        # All enrichments enabled, limits matching original hard-coded values.
        # Applied to any stage not listed above — preserves the previous
        # unconditional enrichment behaviour exactly.
        "default": ContextBudget(
            max_total_tokens=8_000,
            include_predecessor=True,
            predecessor_max_chars=2_000,
            include_lessons=True,
            lessons_limit=3,
            include_patterns=True,
            patterns_limit=3,
            include_design=False,
            include_intelligence=False,
            include_clarification=False,
        ),
    }

    # ------------------------------------------------------------------
    # Stage name → budget key  (lowercase → canonical budget key)
    # ------------------------------------------------------------------

    _CANONICAL: dict[str, str] = {
        "clarification":         "clarification",
        "productowner":          "product_owner",
        "product_owner":         "product_owner",
        "architect":             "architect",
        "designer":              "designer",
        "backenddeveloper":      "backend",
        "backend":               "backend",
        "frontenddeveloper":     "frontend",
        "frontend":              "frontend",
        "qa":                    "qa",
        "devops":                "devops",
        "document":              "document",
        # Aliases for stage names used in constants / enums
        "filestructureplanner":  "backend",   # file-planner runs alongside backend
        "sprintplanning":        "architect",  # sprint planning is architecture-adjacent
        "scrummaster":           "default",
        "security":              "architect",
        "buganalyst":            "qa",
    }

    @classmethod
    def get(cls, stage_name: str) -> ContextBudget:
        """Return the :class:`ContextBudget` for *stage_name*.

        Parameters
        ----------
        stage_name:
            Any stage name used in the workflow — ``"Architect"``,
            ``"BackendDeveloper"``, ``"qa"``, etc.  Case-insensitive.

        Returns
        -------
        ContextBudget
            The registered budget for the stage, or ``_BUDGETS["default"]``
            for any unrecognised stage name (preserves previous behaviour).
        """
        key = cls._CANONICAL.get(stage_name.lower(), "default")
        return cls._BUDGETS[key]

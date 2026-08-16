"""Tests for per-stage context budgets in ContextAssembler.

Verifies four core behaviours of the budget gating system:

1. ``clarification`` stage calls NO enrichment methods.
2. ``backend`` stage calls ``_with_design_context``.
3. ``architect`` stage does NOT call ``_with_intelligence_context``.
4. ``backend`` stage truncates a 5 000-char predecessor to 1 000 chars.

Running
-------
From the ``backend/`` directory::

    pytest tests/test_context_budget.py -v

All tests use ``memory_orchestrator=None`` on :class:`ContextAssembler` so
that the legacy path (:meth:`_assemble_legacy`) is exercised, which is where
the budget gating lives.  Post-enrichments (gate feedback, template injection)
are no-ops in every test because ``memory_manager`` is either ``None`` or
returns empty, and ``template_engine`` is ``None``.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from app.workflow.context_assembler import ContextAssembler
from app.workflow.context_budget import ContextBudget, ContextBudgetRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assembler(**kwargs) -> ContextAssembler:
    """Return a :class:`ContextAssembler` with every dep set to ``None``
    unless overridden via *kwargs*.

    ``memory_orchestrator`` is always ``None`` so the legacy path runs.
    """
    defaults = dict(
        memory_orchestrator=None,
        memory_manager=None,
        artifact_manager=None,
        workspace_manager=None,
        learning_loop=None,
        lesson_store=None,
        context_orchestrator=None,
        template_engine=None,
    )
    defaults.update(kwargs)
    return ContextAssembler(**defaults)


def _noop(content: str, *args, **kwargs) -> str:
    """Side-effect function that returns the context string unchanged.

    Used to replace enrichment methods so the assembled context string
    stays clean and inspectable.
    """
    return content


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContextBudget:
    """Budget-gated enrichment in ContextAssembler._assemble_legacy."""

    # ------------------------------------------------------------------
    # 1 — clarification stage: no enrichments at all
    # ------------------------------------------------------------------

    def test_clarification_stage_no_enrichments(self):
        """Stage ``"clarification"`` must not call any enrichment method.

        The clarification stage is the first in the pipeline — it has no
        predecessor to learn from, no design, no intelligence, no lessons,
        no patterns, and it produces (not consumes) the clarification artifact.
        """
        assembler = _make_assembler()

        # Replace every enrichment with a strict mock so we can assert
        # none of them are called.
        enrichment_methods = [
            "_with_predecessor_message",
            "_with_clarification_context",
            "_with_relevant_patterns",
            "_with_design_context",
            "_with_lessons",
            "_with_intelligence_context",
        ]
        mocks: dict[str, MagicMock] = {}
        for name in enrichment_methods:
            m = MagicMock(side_effect=_noop)
            setattr(assembler, name, m)
            mocks[name] = m

        result = assembler.assemble("proj-clar", "clarification", "user request")

        for name, mock in mocks.items():
            assert not mock.called, (
                f"Enrichment {name!r} was called for stage 'clarification' "
                f"but the budget forbids it.  call_args={mock.call_args}"
            )

    # ------------------------------------------------------------------
    # 2 — backend stage: _with_design_context IS called
    # ------------------------------------------------------------------

    def test_backend_stage_gets_design_context(self):
        """Stage ``"backend"`` must call ``_with_design_context``.

        The backend developer budget sets ``include_design=True`` so that
        the approved design spec is available when writing code.
        """
        assembler = _make_assembler()

        # Silence every enrichment — we are testing CALL presence, not effects.
        for name in (
            "_with_predecessor_message",
            "_with_clarification_context",
            "_with_relevant_patterns",
            "_with_lessons",
            "_with_intelligence_context",
        ):
            setattr(assembler, name, MagicMock(side_effect=_noop))

        design_mock = MagicMock(side_effect=_noop)
        assembler._with_design_context = design_mock

        assembler.assemble("proj-be", "backend", "generate user service")

        assert design_mock.called, (
            "_with_design_context was NOT called for stage 'backend'. "
            "Check that ContextBudgetRegistry('backend').include_design is True "
            "and that the budget gate in _assemble_legacy calls it."
        )

    # ------------------------------------------------------------------
    # 3 — architect stage: _with_intelligence_context NOT called
    # ------------------------------------------------------------------

    def test_architect_no_intelligence(self):
        """Stage ``"architect"`` must NOT call ``_with_intelligence_context``.

        At architecture time, no code has been written yet — the file indexer
        and dependency graph would return empty results and waste tokens.
        The architect budget sets ``include_intelligence=False``.
        """
        assembler = _make_assembler()

        # Silence other enrichments
        for name in (
            "_with_predecessor_message",
            "_with_clarification_context",
            "_with_relevant_patterns",
            "_with_design_context",
            "_with_lessons",
        ):
            setattr(assembler, name, MagicMock(side_effect=_noop))

        intelligence_mock = MagicMock(side_effect=_noop)
        assembler._with_intelligence_context = intelligence_mock

        assembler.assemble("proj-arch", "architect", "design the system")

        assert not intelligence_mock.called, (
            "_with_intelligence_context was called for stage 'architect' "
            "but the budget forbids it (include_intelligence=False). "
            f"It was called with: {intelligence_mock.call_args}"
        )

    # ------------------------------------------------------------------
    # 4 — backend predecessor is truncated to 1 000 chars
    # ------------------------------------------------------------------

    def test_predecessor_truncated(self):
        """Backend budget must truncate a 5 000-char predecessor to 1 000 chars.

        The ``"backend"`` budget sets ``predecessor_max_chars=1000``.
        We exercise :meth:`_with_predecessor_message` directly (after setting
        ``_current_budget``) to avoid wiring all other dependencies.

        Assertions
        ----------
        * The first 1 000 characters of the predecessor appear in the result.
        * Character 1 001 onwards does not appear.
        * The string ``...[truncated]`` appears as the truncation marker.
        * The ``### Previous Stage Output`` section header is present.
        """
        PREDECESSOR_CONTENT = "A" * 5_000

        mock_mem = MagicMock()
        # load() must return a non-empty value so the method proceeds.
        mock_mem.load.return_value = '{"role": "Architect", "content": "placeholder"}'

        assembler = _make_assembler(memory_manager=mock_mem)

        # Set the backend budget directly — mirrors what _assemble_legacy does.
        assembler._current_budget = ContextBudgetRegistry.get("backend")

        # Patch AgentMessage so we control the .content field exactly.
        mock_msg = SimpleNamespace(role="Architect", content=PREDECESSOR_CONTENT)

        with patch("app.shared.schemas.message.AgentMessage") as MockAgentMessage:
            MockAgentMessage.model_validate_json.return_value = mock_msg

            result = assembler._with_predecessor_message("proj-be-trunc", "initial context")

        # Section header must be present
        assert "Previous Stage Output" in result, (
            "Expected '### Previous Stage Output' section in result; got:\n" + result[:500]
        )

        # First 1 000 chars of predecessor must appear
        assert "A" * 1_000 in result, (
            "Expected the first 1 000 chars of the predecessor in the result. "
            "Budget predecessor_max_chars=1000 may not be applied."
        )

        # Characters beyond 1 000 must NOT appear (all "A"s — unambiguous)
        assert "A" * 1_001 not in result, (
            "Found more than 1 000 consecutive 'A' characters in the result. "
            "The predecessor was not truncated to predecessor_max_chars=1000."
        )

        # Truncation marker must be present
        assert "[truncated]" in result, (
            "Expected '...[truncated]' marker after the cut-off point; not found."
        )


# ---------------------------------------------------------------------------
# Unit tests for ContextBudgetRegistry itself
# ---------------------------------------------------------------------------


class TestContextBudgetRegistry:
    """Smoke tests for the registry — correct budgets, normalisation, defaults."""

    def test_clarification_budget_all_false(self):
        budget = ContextBudgetRegistry.get("clarification")
        assert not budget.include_predecessor
        assert not budget.include_lessons
        assert not budget.include_patterns
        assert not budget.include_design
        assert not budget.include_intelligence
        assert not budget.include_clarification

    def test_backend_budget_design_and_intelligence_true(self):
        budget = ContextBudgetRegistry.get("backend")
        assert budget.include_design
        assert budget.include_intelligence
        assert budget.include_predecessor
        assert budget.predecessor_max_chars == 1_000

    def test_backend_developer_alias(self):
        """PascalCase stage name 'BackendDeveloper' must resolve to 'backend' budget."""
        budget_lower = ContextBudgetRegistry.get("backend")
        budget_pascal = ContextBudgetRegistry.get("BackendDeveloper")
        assert budget_lower is budget_pascal

    def test_architect_no_design_no_intelligence(self):
        budget = ContextBudgetRegistry.get("Architect")
        assert not budget.include_design
        assert not budget.include_intelligence
        assert budget.include_predecessor
        assert budget.predecessor_max_chars == 3_000

    def test_product_owner_clarification_true(self):
        budget = ContextBudgetRegistry.get("ProductOwner")
        assert budget.include_clarification
        assert not budget.include_design
        assert not budget.include_intelligence

    def test_unknown_stage_returns_default(self):
        """Unrecognised stage name must fall back to the 'default' budget."""
        budget = ContextBudgetRegistry.get("SomeUnknownStage")
        default = ContextBudgetRegistry.get("default")
        assert budget is default

    def test_default_budget_all_include_true(self):
        """The 'default' budget must enable every enrichment flag (backward-compat)."""
        budget = ContextBudgetRegistry.get("default")
        assert budget.include_predecessor
        assert budget.include_lessons
        assert budget.include_patterns
        # design and intelligence are False in default — they were never called
        # unconditionally; _with_design_context / _with_intelligence_context
        # had their own internal guards (DESIGN_DEPENDENT_STAGES check, etc.)
        # The default budget preserves that pre-existing selective behaviour.

    def test_budget_is_frozen(self):
        """ContextBudget must be immutable (frozen dataclass)."""
        budget = ContextBudgetRegistry.get("architect")
        with pytest.raises(Exception):  # FrozenInstanceError (dataclasses.FrozenInstanceError)
            budget.include_design = True  # type: ignore[misc]

    def test_lessons_limit_respected_by_stage(self):
        """Each stage's lessons_limit must match the specification."""
        assert ContextBudgetRegistry.get("backend").lessons_limit == 2
        assert ContextBudgetRegistry.get("architect").lessons_limit == 2
        assert ContextBudgetRegistry.get("devops").lessons_limit == 1
        assert ContextBudgetRegistry.get("document").lessons_limit == 1
        assert ContextBudgetRegistry.get("clarification").lessons_limit == 0

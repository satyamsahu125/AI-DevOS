"""test_sprint_scoped_memory_loading.py — Sprint-scoped episodic memory loading.

Verifies that MemoryOrchestrator._load_predecessor_outputs() reads sprint-stage
predecessors from sprint-scoped keys, preventing Sprint 1 data from leaking
into Sprint 2 agent context.

Scenarios covered:
  1. Sprint 1 loads Sprint 1 sprint-stage episodic memory.
  2. Sprint 2 loads Sprint 2 sprint-stage episodic memory.
  3. Sprint 2 does NOT receive Sprint 1 sprint-stage episodic memory.
  4. Canonical discovery stages always use project-level keys (cross-sprint).
  5. Missing current_sprint_number does not crash; falls back to canonical key.
  6. Existing context behaviour for non-sprint stages is unchanged.
  7. get_context() end-to-end returns sprint-isolated predecessor_outputs.

Running:
    cd backend
    python -m pytest tests/test_sprint_scoped_memory_loading.py -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.memory.manager import MemoryManager
from app.memory.orchestrator import MemoryOrchestrator, _SPRINT_STAGES
from app.shared.enums.stage import Stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memory_manager() -> MemoryManager:
    return MemoryManager(root=Path(tempfile.mkdtemp()))


def _make_workspace(sprint_number: int | None = None, raises: bool = False) -> MagicMock:
    ws = MagicMock()
    if raises:
        ws.load_project_json.side_effect = RuntimeError("no disk")
    else:
        pj: dict = {}
        if sprint_number is not None:
            pj["current_sprint_number"] = sprint_number
            pj["original_request"] = "build something"
        ws.load_project_json.return_value = pj
    return ws


def _make_orchestrator(
    mm: MemoryManager,
    sprint_number: int | None = None,
    ws_raises: bool = False,
) -> MemoryOrchestrator:
    return MemoryOrchestrator(
        memory_manager=mm,
        workspace_manager=_make_workspace(sprint_number, ws_raises),
    )


def _write_sprint_output(mm: MemoryManager, project_id: str, sprint: int, stage: str, payload: dict) -> None:
    """Write sprint-scoped memory entry (as MemoryOrchestrator.record_approval would)."""
    mm.store_sprint_stage_output(project_id, sprint, stage, json.dumps(payload))


def _write_canonical_output(mm: MemoryManager, project_id: str, stage: str, payload: dict) -> None:
    """Write canonical memory entry."""
    mm.store_stage_output(project_id, stage, json.dumps(payload))


# ---------------------------------------------------------------------------
# Sprint-scoped predecessor loading
# ---------------------------------------------------------------------------

class TestSprintScopedLoading:
    """Stage enum order: ProductOwner(1) Architect(3) BackendDeveloper(5) FrontendDeveloper(6) QA(7).
    Valid sprint-stage predecessor pairs: BackendDeveloper → FrontendDeveloper, and both → QA.
    """

    def test_sprint1_loads_sprint1_episodic_output(self):
        """FrontendDeveloper in Sprint 1 must receive Sprint 1 BackendDeveloper output."""
        mm = _make_memory_manager()
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"sprint": 1, "data": "s1-backend"})
        _write_sprint_output(mm, "proj-1", 2, "BackendDeveloper", {"sprint": 2, "data": "s2-backend"})

        orch = _make_orchestrator(mm, sprint_number=1)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" in outputs
        assert outputs["BackendDeveloper"]["sprint"] == 1
        assert outputs["BackendDeveloper"]["data"] == "s1-backend"

    def test_sprint2_loads_sprint2_episodic_output(self):
        """FrontendDeveloper in Sprint 2 must receive Sprint 2 BackendDeveloper output."""
        mm = _make_memory_manager()
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"sprint": 1, "data": "s1-backend"})
        _write_sprint_output(mm, "proj-1", 2, "BackendDeveloper", {"sprint": 2, "data": "s2-backend"})

        orch = _make_orchestrator(mm, sprint_number=2)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" in outputs
        assert outputs["BackendDeveloper"]["sprint"] == 2

    def test_sprint2_does_not_receive_sprint1_output(self):
        """Sprint 2 predecessor context must never contain Sprint 1 sprint-stage data."""
        mm = _make_memory_manager()
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"sprint": 1, "secret": "sprint1-only"})
        # Sprint 2 has NOT run BackendDeveloper yet — no sprint-scoped key for sprint 2

        orch = _make_orchestrator(mm, sprint_number=2)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        # Sprint 2 should see nothing for BackendDeveloper (not yet run in Sprint 2)
        assert "BackendDeveloper" not in outputs

    def test_sprint1_and_sprint2_outputs_are_independent(self):
        """Loading Sprint 1 vs Sprint 2 must return completely independent data.

        BackendDeveloper (position 5) is a valid sprint-stage predecessor of
        FrontendDeveloper (position 6) and QA (position 7).
        """
        mm = _make_memory_manager()
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"plan": "sprint1-plan"})
        _write_sprint_output(mm, "proj-1", 2, "BackendDeveloper", {"plan": "sprint2-plan"})

        orch1 = _make_orchestrator(mm, sprint_number=1)
        orch2 = _make_orchestrator(mm, sprint_number=2)

        # FrontendDeveloper (6) loads BackendDeveloper (5) as predecessor
        out1 = orch1._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)
        out2 = orch2._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert out1["BackendDeveloper"]["plan"] == "sprint1-plan"
        assert out2["BackendDeveloper"]["plan"] == "sprint2-plan"


# ---------------------------------------------------------------------------
# Canonical (cross-sprint) stage loading
# ---------------------------------------------------------------------------

class TestCanonicalStageLoading:

    def test_discovery_stages_use_canonical_key(self):
        """Architect output must be loaded from the canonical key regardless of sprint."""
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "Architect", {"spec": "arch-spec"})

        orch = _make_orchestrator(mm, sprint_number=2)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.BackendDeveloper)

        assert "Architect" in outputs
        assert outputs["Architect"]["spec"] == "arch-spec"

    def test_product_owner_canonical_available_in_sprint2(self):
        """ProductOwner canonical output must be visible to Sprint 2 agents."""
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "ProductOwner", {"req": "build a todo app"})

        orch = _make_orchestrator(mm, sprint_number=2)
        # FrontendDeveloper loads predecessors including ProductOwner
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert "ProductOwner" in outputs
        assert outputs["ProductOwner"]["req"] == "build a todo app"

    def test_product_owner_canonical_available_across_sprints(self):
        """ProductOwner (position 1) canonical output must be visible to Architect (position 3) in any sprint.

        Note: StrategicReview is position 9 in the enum — it comes AFTER Architect
        (position 3) so it is never a predecessor of Architect.  ProductOwner (1)
        is a valid predecessor of Architect (3).
        """
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "ProductOwner", {"brief": "strategy"})

        for sprint in (1, 2, 3):
            orch = _make_orchestrator(mm, sprint_number=sprint)
            outputs = orch._load_predecessor_outputs("proj-1", Stage.Architect)
            assert "ProductOwner" in outputs, f"Sprint {sprint} must see ProductOwner"


# ---------------------------------------------------------------------------
# Fallback / backward compatibility
# ---------------------------------------------------------------------------

class TestFallbackBehavior:

    def test_no_sprint_number_falls_back_to_canonical(self):
        """Without current_sprint_number, sprint-stage predecessors use canonical key."""
        mm = _make_memory_manager()
        # Only canonical key exists (pre-Phase-2 style)
        _write_canonical_output(mm, "proj-1", "BackendDeveloper", {"code": "canonical-backend"})

        orch = _make_orchestrator(mm, sprint_number=None)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" in outputs
        assert outputs["BackendDeveloper"]["code"] == "canonical-backend"

    def test_workspace_failure_falls_back_to_canonical(self):
        """When workspace_manager raises, sprint-stage loading falls back to canonical.

        BackendDeveloper (5) is a sprint stage and a valid predecessor of
        FrontendDeveloper (6).  When sprint context is unavailable (workspace
        raises), we fall back to the canonical key.
        """
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "BackendDeveloper", {"plan": "fallback-plan"})

        orch = _make_orchestrator(mm, sprint_number=1, ws_raises=True)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" in outputs
        assert outputs["BackendDeveloper"]["plan"] == "fallback-plan"

    def test_no_crash_when_sprint_scoped_key_missing(self):
        """Missing sprint-scoped key must return no output, not raise."""
        mm = _make_memory_manager()
        # No sprint-scoped or canonical entry for BackendDeveloper

        orch = _make_orchestrator(mm, sprint_number=1)
        outputs = orch._load_predecessor_outputs("proj-1", Stage.FrontendDeveloper)

        # BackendDeveloper simply absent — no crash
        assert "BackendDeveloper" not in outputs

    def test_non_sprint_stage_context_unaffected(self):
        """For a canonical current stage (Architect pos 3), predecessors use canonical keys.

        Architect's predecessors in enum order: ProductOwner (1), Reviewer (2).
        StrategicReview is position 9 (after Architect) — NOT a predecessor.
        """
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "ProductOwner", {"req": "requirements"})

        orch = _make_orchestrator(mm, sprint_number=1)
        # Architect is a canonical stage; its predecessors are also canonical
        outputs = orch._load_predecessor_outputs("proj-1", Stage.Architect)

        assert "ProductOwner" in outputs


# ---------------------------------------------------------------------------
# get_context() end-to-end integration
# ---------------------------------------------------------------------------

class TestGetContextEndToEnd:

    def test_get_context_returns_sprint_isolated_predecessors(self):
        """get_context() predecessor_outputs must be sprint-isolated for sprint stages.

        BackendDeveloper (5) is a sprint-stage predecessor of FrontendDeveloper (6).
        """
        mm = _make_memory_manager()
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"plan": "sprint1"})
        _write_sprint_output(mm, "proj-1", 2, "BackendDeveloper", {"plan": "sprint2"})

        orch = MemoryOrchestrator(
            memory_manager=mm,
            workspace_manager=_make_workspace(sprint_number=2),
        )
        ctx = orch.get_context("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" in ctx.predecessor_outputs
        assert ctx.predecessor_outputs["BackendDeveloper"]["plan"] == "sprint2"

    def test_get_context_sprint2_does_not_see_sprint1_predecessor(self):
        """get_context() in Sprint 2 must exclude Sprint 1 sprint-stage outputs."""
        mm = _make_memory_manager()
        # Only Sprint 1 data exists for BackendDeveloper; Sprint 2 hasn't run it yet
        _write_sprint_output(mm, "proj-1", 1, "BackendDeveloper", {"plan": "sprint1-only"})

        orch = MemoryOrchestrator(
            memory_manager=mm,
            workspace_manager=_make_workspace(sprint_number=2),
        )
        ctx = orch.get_context("proj-1", Stage.FrontendDeveloper)

        assert "BackendDeveloper" not in ctx.predecessor_outputs

    def test_get_context_canonical_still_present_in_sprint2(self):
        """get_context() in Sprint 2 must still include canonical discovery artifacts.

        Architect (3) is a canonical predecessor of BackendDeveloper (5).
        BackendDeveloper (5) is a sprint-stage predecessor of FrontendDeveloper (6).
        """
        mm = _make_memory_manager()
        _write_canonical_output(mm, "proj-1", "Architect", {"spec": "arch"})
        _write_sprint_output(mm, "proj-1", 2, "BackendDeveloper", {"code": "sprint2-code"})

        orch = MemoryOrchestrator(
            memory_manager=mm,
            workspace_manager=_make_workspace(sprint_number=2),
        )
        ctx = orch.get_context("proj-1", Stage.FrontendDeveloper)

        assert "Architect" in ctx.predecessor_outputs
        assert "BackendDeveloper" in ctx.predecessor_outputs

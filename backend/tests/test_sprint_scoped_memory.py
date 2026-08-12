"""test_sprint_scoped_memory.py — Sprint-scoped MemoryManager keys.

Verifies:
  1. Sprint 1 and Sprint 2 stage outputs are stored under different keys.
  2. Loading Sprint 2 key returns Sprint 2 data, not Sprint 1.
  3. Canonical cross-sprint memory (architecture, discovery stages) remains
     accessible via the existing load_stage_output path.
  4. Existing memory behavior is compatible — canonical key written alongside
     sprint-scoped key when sprint context is active.
  5. Missing sprint information (no current_sprint_number in project.json)
     does not crash record_approval().
  6. Non-sprint stages (canonical discovery) do NOT get sprint-scoped writes.
  7. MemoryOrchestrator.record_approval() writes sprint-scoped key for sprint
     stages when sprint context is active.

Running:
    cd backend
    python -m pytest tests/test_sprint_scoped_memory.py -v
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
    """Return an in-memory-backed MemoryManager using a temp SQLite file."""
    td = tempfile.mkdtemp()
    return MemoryManager(root=Path(td))


def _make_orchestrator(
    sprint_number: int | None = None,
    workspace_raises: bool = False,
) -> tuple[MemoryOrchestrator, MemoryManager]:
    """Build a MemoryOrchestrator with real MemoryManager and mocked workspace.

    sprint_number: value stored as current_sprint_number in project.json mock.
    workspace_raises: if True, load_project_json raises an exception.
    """
    memory_manager = _make_memory_manager()

    workspace = MagicMock()
    if workspace_raises:
        workspace.load_project_json.side_effect = RuntimeError("disk failure")
    else:
        pj: dict = {}
        if sprint_number is not None:
            pj["current_sprint_number"] = sprint_number
        workspace.load_project_json.return_value = pj

    orchestrator = MemoryOrchestrator(
        memory_manager=memory_manager,
        workspace_manager=workspace,
    )
    return orchestrator, memory_manager


# ---------------------------------------------------------------------------
# MemoryManager — sprint-scoped key isolation
# ---------------------------------------------------------------------------

class TestMemoryManagerSprintScoping:

    def test_sprint1_and_sprint2_use_different_keys(self):
        """Storing Sprint 1 and Sprint 2 outputs for the same stage must not collide."""
        mm = _make_memory_manager()
        mm.store_sprint_stage_output("proj-1", 1, "BackendDeveloper", "sprint1-backend")
        mm.store_sprint_stage_output("proj-1", 2, "BackendDeveloper", "sprint2-backend")

        assert mm.load_sprint_stage_output("proj-1", 1, "BackendDeveloper") == "sprint1-backend"
        assert mm.load_sprint_stage_output("proj-1", 2, "BackendDeveloper") == "sprint2-backend"

    def test_loading_sprint2_does_not_return_sprint1(self):
        """load_sprint_stage_output(sprint=2) must never return Sprint 1 data."""
        mm = _make_memory_manager()
        mm.store_sprint_stage_output("proj-1", 1, "FrontendDeveloper", "sprint1-frontend")
        mm.store_sprint_stage_output("proj-1", 2, "FrontendDeveloper", "sprint2-frontend")

        result = mm.load_sprint_stage_output("proj-1", 2, "FrontendDeveloper")
        assert result == "sprint2-frontend"
        assert "sprint1-frontend" not in (result or "")

    def test_loading_sprint1_does_not_return_sprint2(self):
        """load_sprint_stage_output(sprint=1) must never return Sprint 2 data."""
        mm = _make_memory_manager()
        mm.store_sprint_stage_output("proj-1", 1, "BackendDeveloper", "s1-data")
        mm.store_sprint_stage_output("proj-1", 2, "BackendDeveloper", "s2-data")

        result = mm.load_sprint_stage_output("proj-1", 1, "BackendDeveloper")
        assert result == "s1-data"

    def test_missing_sprint_key_returns_none(self):
        """Loading a sprint-scoped key that was never written must return None."""
        mm = _make_memory_manager()
        result = mm.load_sprint_stage_output("proj-1", 99, "BackendDeveloper")
        assert result is None

    def test_project_isolation_preserved(self):
        """Sprint-scoped keys must be namespaced per project_id."""
        mm = _make_memory_manager()
        mm.store_sprint_stage_output("proj-A", 1, "BackendDeveloper", "proj-a data")
        mm.store_sprint_stage_output("proj-B", 1, "BackendDeveloper", "proj-b data")

        assert mm.load_sprint_stage_output("proj-A", 1, "BackendDeveloper") == "proj-a data"
        assert mm.load_sprint_stage_output("proj-B", 1, "BackendDeveloper") == "proj-b data"

    def test_canonical_key_unaffected_by_sprint_write(self):
        """Writing sprint-scoped key must not affect the canonical stage key."""
        mm = _make_memory_manager()
        mm.store_stage_output("proj-1", "Architect", "canonical-arch")
        mm.store_sprint_stage_output("proj-1", 1, "Architect", "sprint-scoped-arch")

        # Canonical key still returns original value
        assert mm.load_stage_output("proj-1", "Architect") == "canonical-arch"
        # Sprint-scoped key returns its own value
        assert mm.load_sprint_stage_output("proj-1", 1, "Architect") == "sprint-scoped-arch"

    def test_sprint_scoped_key_format(self):
        """The sprint-scoped key must use the expected pattern."""
        mm = _make_memory_manager()
        mm.store_sprint_stage_output("proj-1", 3, "QA", "qa-output")
        # Load using the underlying generic load to inspect the actual key
        raw = mm.load("proj-1", "sprint:3:stage:QA")
        assert raw == "qa-output"


# ---------------------------------------------------------------------------
# MemoryOrchestrator — record_approval() sprint-scoped writes
# ---------------------------------------------------------------------------

class TestMemoryOrchestratorSprintScoping:

    def test_sprint_stage_gets_sprint_scoped_write(self):
        """record_approval() for a sprint stage must write sprint-scoped key."""
        orch, mm = _make_orchestrator(sprint_number=1)
        orch.record_approval("proj-1", Stage.BackendDeveloper, {"code": "hello"})

        result = mm.load_sprint_stage_output("proj-1", 1, "BackendDeveloper")
        assert result is not None
        data = json.loads(result)
        assert data["code"] == "hello"

    def test_sprint_stage_also_writes_canonical_key(self):
        """record_approval() must ALSO write the canonical key for backward compat."""
        orch, mm = _make_orchestrator(sprint_number=1)
        orch.record_approval("proj-1", Stage.BackendDeveloper, {"code": "hi"})

        canonical = mm.load_stage_output("proj-1", "BackendDeveloper")
        assert canonical is not None
        assert json.loads(canonical)["code"] == "hi"

    def test_sprint2_output_isolated_from_sprint1(self):
        """Sprint 2 record_approval must not overwrite Sprint 1's sprint-scoped key."""
        orch, mm = _make_orchestrator(sprint_number=1)
        orch.record_approval("proj-1", Stage.BackendDeveloper, {"sprint": 1})

        # Simulate moving to sprint 2: create new orchestrator with sprint_number=2
        orch2, mm2 = _make_orchestrator(sprint_number=2)
        # Inject the SAME memory manager so both sprints share storage
        orch2.memory_manager = mm
        orch2.record_approval("proj-1", Stage.BackendDeveloper, {"sprint": 2})

        sprint1_data = json.loads(mm.load_sprint_stage_output("proj-1", 1, "BackendDeveloper"))
        sprint2_data = json.loads(mm.load_sprint_stage_output("proj-1", 2, "BackendDeveloper"))

        assert sprint1_data["sprint"] == 1
        assert sprint2_data["sprint"] == 2

    def test_canonical_stage_does_not_get_sprint_scoped_write(self):
        """Canonical discovery stages (Architect, ProductOwner) must not get sprint-scoped writes."""
        orch, mm = _make_orchestrator(sprint_number=1)
        orch.record_approval("proj-1", Stage.Architect, {"spec": "arch"})

        # No sprint-scoped key should exist for Architect
        result = mm.load_sprint_stage_output("proj-1", 1, "Architect")
        assert result is None

        # Canonical key must still be written
        canonical = mm.load_stage_output("proj-1", "Architect")
        assert canonical is not None

    def test_no_sprint_number_does_not_crash(self):
        """record_approval() when no current_sprint_number in project.json must not raise."""
        orch, mm = _make_orchestrator(sprint_number=None)
        orch.record_approval("proj-1", Stage.BackendDeveloper, {"code": "ok"})

        # Sprint-scoped key must not have been written (sprint_number is None)
        assert mm.load_sprint_stage_output("proj-1", 0, "BackendDeveloper") is None

        # Canonical key must still be written
        canonical = mm.load_stage_output("proj-1", "BackendDeveloper")
        assert canonical is not None

    def test_workspace_failure_does_not_crash(self):
        """record_approval() must succeed even when workspace_manager.load_project_json raises."""
        orch, mm = _make_orchestrator(sprint_number=1, workspace_raises=True)
        # Must not raise
        orch.record_approval("proj-1", Stage.BackendDeveloper, {"code": "ok"})

        # Canonical key still written
        canonical = mm.load_stage_output("proj-1", "BackendDeveloper")
        assert canonical is not None

    def test_sprint_stages_constant_covers_expected_stages(self):
        """_SPRINT_STAGES must contain all expected episodic sprint stage names."""
        expected = {
            "BackendDeveloper", "FrontendDeveloper", "QA", "ScrumMaster",
            "SprintDeploy", "SprintReview", "SprintDelta", "FileStructurePlanner",
        }
        assert expected.issubset(_SPRINT_STAGES), (
            f"Missing sprint stages: {expected - _SPRINT_STAGES}"
        )

    def test_canonical_stages_not_in_sprint_stages(self):
        """Discovery stages must NOT appear in _SPRINT_STAGES."""
        canonical = {"Architect", "ProductOwner", "Designer", "StrategicReview"}
        overlap = canonical & _SPRINT_STAGES
        assert overlap == set(), f"Canonical stages incorrectly in _SPRINT_STAGES: {overlap}"

"""test_stale_artifact_detection.py — Stale artifact detection and context filtering.

Verifies:
  1. StageArtifact.is_stale() staleness rules (all 4 branches).
  2. ContextOrchestrator._load_stage_artifacts() excludes stale artifacts.
  3. ContextOrchestrator._load_stage_artifacts() includes matching-version artifacts.
  4. Legacy artifacts (no requirement_version_id) are always included.
  5. No current_version_id on project → no crash, all artifacts treated as active.
  6. ContextOrchestrator.build() end-to-end: stale artifacts absent from package.
  7. ContextOrchestrator.build() end-to-end: valid artifacts present in package.
  8. Existing build() behavior unaffected when versioning is not in use.

Running:
    cd backend
    python -m pytest tests/test_stale_artifact_detection.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.intelligence.context_orchestrator import ContextOrchestrator
from app.shared.enums.artifact_status import ArtifactStatus
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CURRENT_VID = "req-v-current-001"
_OLD_VID = "req-v-old-999"


def _artifact(
    stage_value: str = "ProductOwner",
    content: str = "spec content",
    requirement_version_id: str | None = None,
) -> StageArtifact:
    return StageArtifact(
        artifact_id="test-id",
        name=stage_value,
        content=content,
        status=ArtifactStatus.Stored,
        project_id="proj-1",
        requirement_version_id=requirement_version_id,
    )


def _make_orchestrator(
    artifact_map: dict[str, StageArtifact | None],
    current_version_id: str | None = _CURRENT_VID,
    workspace_raises: bool = False,
) -> ContextOrchestrator:
    """Build a ContextOrchestrator with all heavy deps mocked.

    artifact_map: stage enum value → StageArtifact (or None) returned by
                  artifact_manager.get_artifact().
    current_version_id: value stored in project.json.
    """
    artifact_manager = MagicMock()
    def _get_artifact(project_id, stage_enum):
        return artifact_map.get(stage_enum.value)
    artifact_manager.get_artifact.side_effect = _get_artifact

    workspace = MagicMock()
    if workspace_raises:
        workspace.load_project_json.side_effect = RuntimeError("no disk")
    else:
        pj: dict = {}
        if current_version_id is not None:
            pj["current_requirement_version_id"] = current_version_id
        workspace.load_project_json.return_value = pj

    summarizer = MagicMock()
    summarizer.build_project_overview.return_value = "overview"
    summarizer.get_relevant_files.return_value = []

    orchestrator = ContextOrchestrator(
        file_indexer=MagicMock(),
        dependency_graph=MagicMock(),
        code_summarizer=summarizer,
        knowledge_memory=MagicMock(),
        lesson_store=MagicMock(),
        artifact_manager=artifact_manager,
        workspace_manager=workspace,
    )
    return orchestrator


# ---------------------------------------------------------------------------
# StageArtifact.is_stale() unit tests
# ---------------------------------------------------------------------------

class TestIsStale:

    def test_matching_version_not_stale(self):
        art = _artifact(requirement_version_id=_CURRENT_VID)
        assert art.is_stale(_CURRENT_VID) is False

    def test_mismatched_version_is_stale(self):
        art = _artifact(requirement_version_id=_OLD_VID)
        assert art.is_stale(_CURRENT_VID) is True

    def test_legacy_artifact_no_version_never_stale(self):
        """Artifact without requirement_version_id must never be considered stale."""
        art = _artifact(requirement_version_id=None)
        assert art.is_stale(_CURRENT_VID) is False

    def test_no_current_version_never_stale(self):
        """When the project has no current_version_id, nothing can be stale."""
        art = _artifact(requirement_version_id=_OLD_VID)
        assert art.is_stale(None) is False

    def test_both_none_never_stale(self):
        art = _artifact(requirement_version_id=None)
        assert art.is_stale(None) is False


# ---------------------------------------------------------------------------
# _load_stage_artifacts() filtering
# ---------------------------------------------------------------------------

class TestLoadStageArtifactsFiltering:
    """Tests _load_stage_artifacts() in isolation via direct call.

    Stage "devops" needs ["architect", "security"] — both resolve correctly in
    the existing lookup (single-word PascalCase, no underscore).  Multi-word
    stage names (product_owner, file_planner) are UNRESOLVABLE in the
    pre-existing lookup logic and are intentionally avoided here.
    """

    def test_matching_version_artifact_included(self):
        """An artifact whose version matches current must appear in context."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "arch spec", requirement_version_id=_CURRENT_VID)},
            current_version_id=_CURRENT_VID,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=_CURRENT_VID)
        assert "architect" in result
        assert "arch spec" in result["architect"]

    def test_stale_artifact_excluded(self):
        """An artifact produced for an older version must be excluded."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "old arch", requirement_version_id=_OLD_VID)},
            current_version_id=_CURRENT_VID,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=_CURRENT_VID)
        assert "architect" not in result

    def test_legacy_artifact_included(self):
        """Artifact with no requirement_version_id must always be included."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "legacy arch", requirement_version_id=None)},
            current_version_id=_CURRENT_VID,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=_CURRENT_VID)
        assert "architect" in result

    def test_no_current_version_all_artifacts_included(self):
        """When current_version_id is None, no staleness check — all artifacts active."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "arch spec", requirement_version_id=_OLD_VID)},
            current_version_id=None,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=None)
        assert "architect" in result

    def test_none_artifact_skipped(self):
        """When artifact_manager returns None for a stage, it must be silently skipped."""
        orch = _make_orchestrator(
            artifact_map={"Architect": None},
            current_version_id=_CURRENT_VID,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=_CURRENT_VID)
        assert "architect" not in result

    def test_mixed_stale_and_fresh(self):
        """Only fresh artifacts must appear when some are stale and some are not.

        "devops" needs ["architect", "security"] — both resolve.
        architect → current version → included
        security  → old version    → excluded
        """
        orch = _make_orchestrator(
            artifact_map={
                "Architect": _artifact("Architect", "arch spec", requirement_version_id=_CURRENT_VID),
                "Security":  _artifact("Security",  "sec spec",  requirement_version_id=_OLD_VID),
            },
            current_version_id=_CURRENT_VID,
        )
        result = orch._load_stage_artifacts("proj-1", "devops", current_version_id=_CURRENT_VID)
        assert "architect" in result      # matching version → included
        assert "security" not in result   # old version → excluded


# ---------------------------------------------------------------------------
# build() end-to-end integration
# ---------------------------------------------------------------------------

class TestBuildEndToEnd:
    """End-to-end tests through build().

    Uses "devops" stage (needs "architect" and "security") because those stage
    names resolve correctly in the pre-existing lookup logic.
    """

    def test_build_excludes_stale_artifact_from_package(self):
        """build() must not include a stale artifact in the returned ContextPackage."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "old arch", requirement_version_id=_OLD_VID)},
            current_version_id=_CURRENT_VID,
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        package = orch.build("proj-1", "devops", "deploy the app")
        assert "architect" not in package.stage_artifacts

    def test_build_includes_valid_artifact_in_package(self):
        """build() must include an artifact whose version matches current."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "current arch", requirement_version_id=_CURRENT_VID)},
            current_version_id=_CURRENT_VID,
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        package = orch.build("proj-1", "devops", "deploy the app")
        assert "architect" in package.stage_artifacts
        assert "current arch" in package.stage_artifacts["architect"]

    def test_build_includes_legacy_artifact_in_package(self):
        """build() must include a legacy artifact (no version) in the package."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "legacy arch", requirement_version_id=None)},
            current_version_id=_CURRENT_VID,
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        package = orch.build("proj-1", "devops", "deploy the app")
        assert "architect" in package.stage_artifacts

    def test_build_no_crash_when_workspace_unavailable(self):
        """build() must not crash when workspace_manager.load_project_json raises."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "arch spec", requirement_version_id=_OLD_VID)},
            current_version_id=_CURRENT_VID,
            workspace_raises=True,
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        # Should not raise; stale check falls back to treating all as active (current_version_id=None)
        package = orch.build("proj-1", "devops", "deploy the app")
        assert isinstance(package.stage_artifacts, dict)

    def test_build_no_versioning_active_behavior_unchanged(self):
        """When no current_version_id exists, build() behaves exactly as before."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "arch spec", requirement_version_id=None)},
            current_version_id=None,  # versioning not active
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        package = orch.build("proj-1", "devops", "deploy the app")
        assert "architect" in package.stage_artifacts

    def test_build_project_json_loaded_once(self):
        """build() must call load_project_json exactly once (no duplicate reads)."""
        orch = _make_orchestrator(
            artifact_map={"Architect": _artifact("Architect", "arch spec", requirement_version_id=_CURRENT_VID)},
            current_version_id=_CURRENT_VID,
        )
        orch.knowledge.search.return_value = []
        orch.lessons.get_lessons.return_value = []

        orch.build("proj-1", "devops", "deploy the app")
        assert orch.workspace.load_project_json.call_count == 1

"""test_phase8_write_mode.py — P8-2c and P8-3 regression tests.

Covers:
  P8-2c  ProjectFileManager.write_file() write_mode parameter:
           - write_mode="create" + existing file → no-op (bytes_written=0, file unchanged)
           - write_mode="create" + missing file  → normal write
           - write_mode="overwrite"              → replaces existing file (default behavior)
           - write_mode="patch"                  → writes supplied content (same as overwrite)

  P8-3   WriteProjectFilesAction operation → write_mode mapping:
           - planned create  → write_mode="create"
           - planned update  → write_mode="overwrite"
           - planned patch   → write_mode="patch"
           - existing update/patch content injection still works

Running:
    cd backend
    python -m pytest tests/test_phase8_write_mode.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project_file_manager(tmp_root: Path):
    """Return a ProjectFileManager whose workspace root is tmp_root."""
    from app.workspace.manager import WorkspaceManager
    from app.workspace.project_files import ProjectFileManager

    ws = WorkspaceManager(root=tmp_root)
    return ProjectFileManager(workspace_manager=ws)


def _project_area_dir(tmp_root: Path, project_id: str, area: str) -> Path:
    """Resolve the exact directory ProjectFileManager would write into."""
    return tmp_root / project_id / "project" / area


# ---------------------------------------------------------------------------
# P8-2c — ProjectFileManager.write_file() write_mode
# ---------------------------------------------------------------------------


class TestWriteFileCreateMode:
    """write_mode='create' must never overwrite an existing file."""

    def test_create_skips_existing_file(self):
        """Given an existing file, write_mode='create' returns bytes_written=0 and leaves content unchanged."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            # Pre-create the file with known content
            target_dir = _project_area_dir(root, "proj-1", "backend")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "models" / "user.py").parent.mkdir(parents=True, exist_ok=True)
            (target_dir / "models" / "user.py").write_text("original content", encoding="utf-8")

            result = pfm.write_file("proj-1", "backend", "models/user.py", "NEW content", write_mode="create")

            assert result.bytes_written == 0
            assert (target_dir / "models" / "user.py").read_text(encoding="utf-8") == "original content"

    def test_create_returns_written_file_with_zero_bytes(self):
        """Return type is WrittenFile with bytes_written=0 (not None, not raised)."""
        from app.workspace.project_files import WrittenFile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            target_dir = _project_area_dir(root, "proj-1", "backend")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "existing.py").write_text("sprint 1 code", encoding="utf-8")

            result = pfm.write_file("proj-1", "backend", "existing.py", "sprint 2 replacement", write_mode="create")

            assert isinstance(result, WrittenFile)
            assert result.bytes_written == 0

    def test_create_writes_missing_file(self):
        """write_mode='create' creates the file when it does not exist."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            result = pfm.write_file("proj-1", "backend", "new_file.py", "brand new content", write_mode="create")

            target = _project_area_dir(root, "proj-1", "backend") / "new_file.py"
            assert result.bytes_written > 0
            assert target.read_text(encoding="utf-8") == "brand new content"

    def test_create_missing_file_returns_correct_byte_count(self):
        """bytes_written matches actual encoded byte count when the file is created."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)
            content = "hello world"

            result = pfm.write_file("proj-1", "backend", "hello.py", content, write_mode="create")

            assert result.bytes_written == len(content.encode("utf-8"))


class TestWriteFileOverwriteMode:
    """write_mode='overwrite' (default) must preserve existing behavior."""

    def test_overwrite_replaces_existing_content(self):
        """write_mode='overwrite' replaces an existing file's content."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            target_dir = _project_area_dir(root, "proj-1", "backend")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "service.py").write_text("old content", encoding="utf-8")

            result = pfm.write_file("proj-1", "backend", "service.py", "new content", write_mode="overwrite")

            assert result.bytes_written > 0
            assert (target_dir / "service.py").read_text(encoding="utf-8") == "new content"

    def test_overwrite_is_default(self):
        """Calling write_file() without write_mode= behaves as overwrite."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            target_dir = _project_area_dir(root, "proj-1", "backend")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "api.py").write_text("original", encoding="utf-8")

            # No write_mode kwarg — must overwrite
            result = pfm.write_file("proj-1", "backend", "api.py", "replaced")

            assert (target_dir / "api.py").read_text(encoding="utf-8") == "replaced"
            assert result.bytes_written > 0

    def test_overwrite_creates_when_missing(self):
        """write_mode='overwrite' creates a new file when absent."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            result = pfm.write_file("proj-1", "backend", "brand_new.py", "content", write_mode="overwrite")

            target = _project_area_dir(root, "proj-1", "backend") / "brand_new.py"
            assert target.exists()
            assert result.bytes_written > 0


class TestWriteFilePatchMode:
    """write_mode='patch' must write the supplied (already-merged) content."""

    def test_patch_writes_supplied_content(self):
        """write_mode='patch' writes the full merged content (no diffing at this layer)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            target_dir = _project_area_dir(root, "proj-1", "backend")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "utils.py").write_text("v1 content", encoding="utf-8")

            merged = "v1 content\n\n# new section\ndef new_func(): pass"
            result = pfm.write_file("proj-1", "backend", "utils.py", merged, write_mode="patch")

            assert (target_dir / "utils.py").read_text(encoding="utf-8") == merged
            assert result.bytes_written > 0

    def test_patch_creates_when_missing(self):
        """write_mode='patch' creates the file when it does not exist."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pfm = _make_project_file_manager(root)

            result = pfm.write_file("proj-1", "backend", "helpers.py", "content", write_mode="patch")

            target = _project_area_dir(root, "proj-1", "backend") / "helpers.py"
            assert target.exists()
            assert result.bytes_written > 0


# ---------------------------------------------------------------------------
# P8-3 — WriteProjectFilesAction operation → write_mode mapping
# ---------------------------------------------------------------------------


class TestActionOperationMapping:
    """WriteProjectFilesAction must pass the correct write_mode to write_file()
    based on planned_file.operation.

    Mapping:
        create → write_mode="create"
        update → write_mode="overwrite"
        patch  → write_mode="patch"
    """

    def _make_planned_file(self, operation: str, path: str = "backend/models/user.py") -> object:
        """Build a minimal PlannedFile-like object with operation, path, purpose, module."""
        from app.shared.schemas.file_plan_schema import PlannedFile
        return PlannedFile(
            path=path,
            module="models",
            purpose="User model",
            responsible_stage="backenddeveloper",
            operation=operation,
            change_description="test change",
        )

    def _make_action(self) -> object:
        """Build a WriteProjectFilesAction with mocked dependencies."""
        from app.actions.write_project_files import WriteProjectFilesAction

        class _ConcreteAction(WriteProjectFilesAction):
            area = "backend"
            responsible_stage = "backenddeveloper"
            role_label = "Backend Developer"
            name = "BackendDeveloper"

        prompt_builder = MagicMock()
        prompt_builder.build.return_value = "prompt text"

        artifact_manager = MagicMock()
        artifact_manager.workspace_manager = MagicMock()
        artifact_manager.workspace_manager.load_project_json.return_value = {}

        project_file_manager = MagicMock()
        # write_file returns a WrittenFile-like result
        from app.workspace.project_files import WrittenFile
        from pathlib import Path as _Path
        project_file_manager.write_file.return_value = WrittenFile(
            path="models/user.py", absolute_path=_Path("/tmp/x"), bytes_written=100
        )
        project_file_manager.read_file.return_value = None
        project_file_manager.file_exists.return_value = False

        file_registry = MagicMock()

        action = _ConcreteAction(
            prompt_builder=prompt_builder,
            artifact_manager=artifact_manager,
            project_file_manager=project_file_manager,
            file_registry=file_registry,
        )
        return action, project_file_manager, artifact_manager, file_registry

    def _make_context(self, project_id: str = "proj-1") -> object:
        ctx = MagicMock()
        ctx.project_id = project_id
        ctx.content = "base content"
        ctx.sprint_number = 1
        return ctx

    def _make_llm(self, content: str = "def user(): pass") -> object:
        llm = MagicMock()
        resp = MagicMock()
        resp.content = content
        resp.total_tokens = 10
        resp.latency = None
        resp.usage = {}
        llm.generate_text.return_value = resp
        return llm

    def _make_file_plan(self, planned_file):
        from app.shared.schemas.file_plan_schema import FilePlanArtifact
        plan = FilePlanArtifact(files=[planned_file])
        return plan

    def _stub_artifact_manager(self, artifact_manager, planned_file):
        """Make artifact_manager.get_artifact() return a plan or None for architecture."""
        from app.shared.schemas.file_plan_schema import FilePlanArtifact

        plan = self._make_file_plan(planned_file)

        def get_artifact(project_id, stage):
            from app.shared.enums.stage import Stage
            if stage == Stage.FileStructurePlanner:
                art = MagicMock()
                art.structured_content = plan.model_dump()
                return art
            return None  # architecture → None is fine

        artifact_manager.get_artifact.side_effect = get_artifact

    def test_create_operation_passes_create_mode(self):
        """planned_file.operation='create' → write_file called with write_mode='create'."""
        action, pfm, am, _ = self._make_action()
        pf = self._make_planned_file("create")
        self._stub_artifact_manager(am, pf)

        ctx = self._make_context()
        llm = self._make_llm("def user(): pass  # long enough content to be plausible")
        action.run(ctx, llm)

        call_kwargs = pfm.write_file.call_args
        assert call_kwargs is not None, "write_file was not called"
        assert call_kwargs.kwargs.get("write_mode") == "create", (
            f"Expected write_mode='create', got {call_kwargs.kwargs.get('write_mode')!r}"
        )

    def test_update_operation_passes_overwrite_mode(self):
        """planned_file.operation='update' → write_file called with write_mode='overwrite'."""
        action, pfm, am, _ = self._make_action()
        # Provide existing content so the update branch is taken
        pfm.read_file.return_value = "existing file content for update"
        pf = self._make_planned_file("update")
        self._stub_artifact_manager(am, pf)

        ctx = self._make_context()
        llm = self._make_llm("def user(): pass  # long enough content to be plausible")
        action.run(ctx, llm)

        call_kwargs = pfm.write_file.call_args
        assert call_kwargs is not None, "write_file was not called"
        assert call_kwargs.kwargs.get("write_mode") == "overwrite", (
            f"Expected write_mode='overwrite', got {call_kwargs.kwargs.get('write_mode')!r}"
        )

    def test_patch_operation_passes_patch_mode(self):
        """planned_file.operation='patch' → write_file called with write_mode='patch'."""
        action, pfm, am, _ = self._make_action()
        pfm.read_file.return_value = "existing content for patch"
        pf = self._make_planned_file("patch")
        self._stub_artifact_manager(am, pf)

        ctx = self._make_context()
        llm = self._make_llm("def user(): pass  # long enough content to be plausible")
        action.run(ctx, llm)

        call_kwargs = pfm.write_file.call_args
        assert call_kwargs is not None, "write_file was not called"
        assert call_kwargs.kwargs.get("write_mode") == "patch", (
            f"Expected write_mode='patch', got {call_kwargs.kwargs.get('write_mode')!r}"
        )

    def test_update_existing_content_injected_in_prompt(self):
        """For operation='update', read_file() is called and existing content is fed to the prompt."""
        action, pfm, am, _ = self._make_action()
        pfm.read_file.return_value = "# Sprint 1 existing content\nclass User: pass"
        pf = self._make_planned_file("update")
        self._stub_artifact_manager(am, pf)

        ctx = self._make_context()
        llm = self._make_llm("class User:\n    id = 1  # long enough content to be plausible for test")
        action.run(ctx, llm)

        # read_file must have been called (existing content injection still works)
        pfm.read_file.assert_called()

    def test_patch_existing_content_injected_in_prompt(self):
        """For operation='patch', read_file() is called and existing content is fed to the prompt."""
        action, pfm, am, _ = self._make_action()
        pfm.read_file.return_value = "# Sprint 1 patch base\ndef helper(): pass"
        pf = self._make_planned_file("patch")
        self._stub_artifact_manager(am, pf)

        ctx = self._make_context()
        llm = self._make_llm("def helper(): pass\ndef new_func(): return 42  # plausible length")
        action.run(ctx, llm)

        pfm.read_file.assert_called()

"""test_phase8_frontend_operation.py — P8-5b regression tests.

Verifies that WriteFrontendCodeAction is operation-aware for update/patch:

  Test 1 — create
    operation="create": no existing-content read, normal generation path works

  Test 2 — update
    operation="update": read_file() called, existing content in prompt,
    change_description in prompt, update instructions present

  Test 3 — patch
    operation="patch": read_file() called, existing content in prompt,
    change in prompt, patch instructions present

  Test 4 — missing existing file (read_file returns None)
    update/patch when existing file absent → no crash, falls back to create prompt

  Test 5 — operation isolation
    create/update/patch paths do not bleed into each other

  Test 6 — mobile area correctness
    For mobile project type (project_type="mobile_app"), _area_for_file_read()
    returns "" (project root) not "frontend"

  Test 7 — web area correctness
    For web project type, _area_for_file_read() returns "frontend"

Running:
    cd backend
    python -m pytest tests/test_phase8_frontend_operation.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_planned_file(operation: str, path: str = "frontend/App.tsx", change_description: str = "add dark mode") -> object:
    from app.shared.schemas.file_plan_schema import PlannedFile
    return PlannedFile(
        path=path,
        module="components",
        purpose="Root application component",
        responsible_stage="frontend",
        operation=operation,
        change_description=change_description,
    )


def _make_architecture(project_type: str = "web_fullstack") -> object:
    from app.shared.schemas.architecture_schema import ArchitectureArtifact
    # Use a real instance so summarize_architecture() can access all fields without
    # MagicMock(spec=...) AttributeErrors from unset instance attributes.
    return ArchitectureArtifact(project_type=project_type)


def _make_frontend_action(
    read_file_return: str | None = "existing content",
) -> tuple:
    """Build a WriteFrontendCodeAction with mocked dependencies.

    Returns (action, project_file_manager_mock, artifact_manager_mock, prompt_builder_mock).
    """
    from app.actions.write_frontend_code import WriteFrontendCodeAction
    from app.workspace.project_files import WrittenFile
    from pathlib import Path

    prompt_builder = MagicMock()
    prompt_builder.build.side_effect = lambda detail: f"BUILT_PROMPT|{detail}"

    artifact_manager = MagicMock()
    artifact_manager.workspace_manager = MagicMock()
    artifact_manager.workspace_manager.load_project_json.return_value = {}
    # No API contract — keeps prompt assembly simple for these tests
    artifact_manager.workspace_manager.get_workspace_path.return_value = MagicMock()

    project_file_manager = MagicMock()
    project_file_manager.write_file.return_value = WrittenFile(
        path="App.tsx", absolute_path=Path("/tmp/x"), bytes_written=100
    )
    project_file_manager.read_file.return_value = read_file_return
    project_file_manager.file_exists.return_value = read_file_return is not None

    action = WriteFrontendCodeAction(
        prompt_builder=prompt_builder,
        artifact_manager=artifact_manager,
        project_file_manager=project_file_manager,
    )
    # Stub out API contract loading so it doesn't inject extra sections
    action._load_api_contract = MagicMock(return_value=None)

    return action, project_file_manager, artifact_manager, prompt_builder


def _invoke_build_file_prompt(action, planned_file, architecture=None, project_id: str = "proj-1") -> str:
    """Call _build_file_prompt() directly and return the resulting prompt string."""
    return action._build_file_prompt(
        planned_file,
        architecture or _make_architecture(),
        "base project context",
        [],
        project_id=project_id,
    )


# ---------------------------------------------------------------------------
# Test 1 — create: no existing-content injection
# ---------------------------------------------------------------------------


class TestFrontendCreate:
    """operation='create' — normal generation, no read_file() call."""

    def test_create_does_not_call_read_file(self):
        """For create operations, read_file() must NOT be called."""
        action, pfm, _, _ = _make_frontend_action()
        pf = _make_planned_file("create")
        _invoke_build_file_prompt(action, pf)
        pfm.read_file.assert_not_called()

    def test_create_prompt_contains_create_operation_label(self):
        """Create prompt must include the CREATE operation label."""
        action, _, _, _ = _make_frontend_action()
        pf = _make_planned_file("create")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "CREATE" in prompt

    def test_create_prompt_does_not_contain_existing_content(self):
        """Create prompt must not contain existing file content."""
        existing = "// Sprint 1 existing code\nconst App = () => null;"
        action, _, _, _ = _make_frontend_action(read_file_return=existing)
        pf = _make_planned_file("create")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "Sprint 1 existing code" not in prompt
        assert "EXISTING FILE CONTENT" not in prompt


# ---------------------------------------------------------------------------
# Test 2 — update: injection, change_description, instructions
# ---------------------------------------------------------------------------


class TestFrontendUpdate:
    """operation='update' — read existing content, inject into prompt."""

    def test_update_calls_read_file(self):
        """For update operations, read_file() must be called."""
        action, pfm, _, _ = _make_frontend_action(read_file_return="existing frontend code")
        pf = _make_planned_file("update")
        _invoke_build_file_prompt(action, pf)
        pfm.read_file.assert_called_once()

    def test_update_existing_content_in_prompt(self):
        """Existing file content must appear in the update prompt."""
        existing = "const Header = () => <h1>Hello</h1>;"
        action, _, _, _ = _make_frontend_action(read_file_return=existing)
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        assert existing in prompt

    def test_update_change_description_in_prompt(self):
        """change_description must appear in the update prompt."""
        action, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf = _make_planned_file("update", change_description="add responsive navbar")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "add responsive navbar" in prompt

    def test_update_prompt_contains_update_label(self):
        """Update prompt must contain the UPDATE operation label."""
        action, _, _, _ = _make_frontend_action(read_file_return="some code")
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "UPDATE" in prompt

    def test_update_prompt_instructs_preserve_functionality(self):
        """Update prompt must instruct the model to preserve existing functionality."""
        action, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        # The parent's prompt says "preserve working functionality"
        assert "preserve" in prompt.lower() or "existing" in prompt.lower()

    def test_update_prompt_requests_complete_file(self):
        """Update prompt must request the COMPLETE updated file, not a diff."""
        action, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "COMPLETE" in prompt.upper()


# ---------------------------------------------------------------------------
# Test 3 — patch: injection, change description, patch instructions
# ---------------------------------------------------------------------------


class TestFrontendPatch:
    """operation='patch' — read existing content, targeted change prompt."""

    def test_patch_calls_read_file(self):
        """For patch operations, read_file() must be called."""
        action, pfm, _, _ = _make_frontend_action(read_file_return="existing code to patch")
        pf = _make_planned_file("patch")
        _invoke_build_file_prompt(action, pf)
        pfm.read_file.assert_called_once()

    def test_patch_existing_content_in_prompt(self):
        """Existing file content must appear in the patch prompt."""
        existing = "export default function Footer() { return <footer />; }"
        action, _, _, _ = _make_frontend_action(read_file_return=existing)
        pf = _make_planned_file("patch")
        prompt = _invoke_build_file_prompt(action, pf)
        assert existing in prompt

    def test_patch_change_description_in_prompt(self):
        """change_description must appear in the patch prompt."""
        action, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf = _make_planned_file("patch", change_description="fix accessibility: add aria-label to button")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "fix accessibility" in prompt or "aria-label" in prompt

    def test_patch_prompt_contains_patch_label(self):
        """Patch prompt must contain the PATCH operation label."""
        action, _, _, _ = _make_frontend_action(read_file_return="some code")
        pf = _make_planned_file("patch")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "PATCH" in prompt

    def test_patch_prompt_instructs_no_unrelated_rewrites(self):
        """Patch prompt must instruct the model not to rewrite unrelated parts."""
        action, _, _, _ = _make_frontend_action(read_file_return="some code")
        pf = _make_planned_file("patch")
        prompt = _invoke_build_file_prompt(action, pf)
        # The parent's patch prompt says "Do NOT rewrite unrelated parts"
        assert "unrelated" in prompt.lower() or "NOT rewrite" in prompt


# ---------------------------------------------------------------------------
# Test 4 — missing existing file (read_file returns None)
# ---------------------------------------------------------------------------


class TestFrontendMissingFile:
    """update/patch when the file doesn't exist yet — must not crash, fall back gracefully."""

    def test_update_missing_file_does_not_raise(self):
        """update when read_file() returns None must not raise."""
        action, _, _, _ = _make_frontend_action(read_file_return=None)
        pf = _make_planned_file("update")
        # Must not raise
        prompt = _invoke_build_file_prompt(action, pf)
        assert isinstance(prompt, str) and len(prompt) > 0

    def test_patch_missing_file_does_not_raise(self):
        """patch when read_file() returns None must not raise."""
        action, _, _, _ = _make_frontend_action(read_file_return=None)
        pf = _make_planned_file("patch")
        prompt = _invoke_build_file_prompt(action, pf)
        assert isinstance(prompt, str) and len(prompt) > 0

    def test_update_missing_file_falls_back_to_create_prompt(self):
        """When existing content unavailable, update falls back to create-style prompt."""
        action, _, _, _ = _make_frontend_action(read_file_return=None)
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        # Parent falls back to CREATE branch when existing_content is None
        assert "EXISTING FILE CONTENT" not in prompt

    def test_update_missing_file_read_file_still_called(self):
        """Even if the file is missing, read_file() must still be called for update."""
        action, pfm, _, _ = _make_frontend_action(read_file_return=None)
        pf = _make_planned_file("update")
        _invoke_build_file_prompt(action, pf)
        pfm.read_file.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5 — operation isolation
# ---------------------------------------------------------------------------


class TestFrontendOperationIsolation:
    """Each operation must produce distinct, non-bleeding prompt content."""

    def test_create_vs_update_prompt_differs(self):
        """create and update prompts must not be identical."""
        action_c, _, _, _ = _make_frontend_action()
        action_u, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf_create = _make_planned_file("create")
        pf_update = _make_planned_file("update")

        create_prompt = _invoke_build_file_prompt(action_c, pf_create)
        update_prompt = _invoke_build_file_prompt(action_u, pf_update)

        assert create_prompt != update_prompt

    def test_update_vs_patch_prompt_differs(self):
        """update and patch prompts must not be identical."""
        action_u, _, _, _ = _make_frontend_action(read_file_return="existing code")
        action_p, _, _, _ = _make_frontend_action(read_file_return="existing code")
        pf_update = _make_planned_file("update")
        pf_patch = _make_planned_file("patch")

        update_prompt = _invoke_build_file_prompt(action_u, pf_update)
        patch_prompt = _invoke_build_file_prompt(action_p, pf_patch)

        assert update_prompt != patch_prompt

    def test_create_does_not_contain_existing_content_section(self):
        """create prompt must never contain EXISTING FILE CONTENT section."""
        action, _, _, _ = _make_frontend_action(read_file_return="should not appear")
        pf = _make_planned_file("create")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "EXISTING FILE CONTENT" not in prompt

    def test_update_contains_existing_content_section(self):
        """update prompt must contain EXISTING FILE CONTENT section."""
        action, _, _, _ = _make_frontend_action(read_file_return="def hello(): pass")
        pf = _make_planned_file("update")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "EXISTING FILE CONTENT" in prompt

    def test_patch_contains_existing_content_section(self):
        """patch prompt must contain EXISTING FILE CONTENT section."""
        action, _, _, _ = _make_frontend_action(read_file_return="def hello(): pass")
        pf = _make_planned_file("patch")
        prompt = _invoke_build_file_prompt(action, pf)
        assert "EXISTING FILE CONTENT" in prompt


# ---------------------------------------------------------------------------
# Test 6 — mobile area correctness
# ---------------------------------------------------------------------------


class TestFrontendMobileArea:
    """_area_for_file_read() must return "" for mobile_app projects."""

    def test_mobile_area_returns_empty_string(self):
        """_area_for_file_read() with mobile_app architecture returns ""."""
        action, _, _, _ = _make_frontend_action()
        arch = _make_architecture(project_type="mobile_app")
        assert action._area_for_file_read(arch) == ""

    def test_mobile_read_file_uses_empty_area(self):
        """For mobile update, read_file() is called with area="" (project root)."""
        action, pfm, _, _ = _make_frontend_action(read_file_return="mobile existing code")
        arch = _make_architecture(project_type="mobile_app")
        pf = _make_planned_file("update", path="App.tsx")

        action._build_file_prompt(pf, arch, "base", [], project_id="proj-1")

        # The area argument to read_file() must be "" for mobile
        call_args = pfm.read_file.call_args
        assert call_args is not None, "read_file was not called for update"
        area_arg = call_args.args[1]  # (project_id, area, path)
        assert area_arg == "", f"Expected area='' for mobile, got {area_arg!r}"

    def test_mobile_area_with_none_architecture_falls_back_to_class_area(self):
        """When architecture=None, _area_for_file_read() falls back to self.area."""
        action, _, _, _ = _make_frontend_action()
        assert action._area_for_file_read(None) == "frontend"


# ---------------------------------------------------------------------------
# Test 7 — web area correctness
# ---------------------------------------------------------------------------


class TestFrontendWebArea:
    """_area_for_file_read() must return "frontend" for web projects."""

    def test_web_fullstack_area_returns_frontend(self):
        action, _, _, _ = _make_frontend_action()
        arch = _make_architecture(project_type="web_fullstack")
        assert action._area_for_file_read(arch) == "frontend"

    def test_web_saas_area_returns_frontend(self):
        action, _, _, _ = _make_frontend_action()
        arch = _make_architecture(project_type="saas")
        assert action._area_for_file_read(arch) == "frontend"

    def test_web_read_file_uses_frontend_area(self):
        """For web update, read_file() is called with area="frontend"."""
        action, pfm, _, _ = _make_frontend_action(read_file_return="web existing code")
        arch = _make_architecture(project_type="web_fullstack")
        pf = _make_planned_file("update", path="frontend/App.tsx")

        action._build_file_prompt(pf, arch, "base", [], project_id="proj-1")

        call_args = pfm.read_file.call_args
        assert call_args is not None, "read_file was not called for update"
        area_arg = call_args.args[1]
        assert area_arg == "frontend", f"Expected area='frontend' for web, got {area_arg!r}"

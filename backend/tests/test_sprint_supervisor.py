"""Tests for SprintSupervisor instantiation and structure.

These tests verify that SprintSupervisor can be created and accessed
correctly. Full integration tests that run the complete sprint loop
with mocked agents are beyond the scope - agent tests are separate.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.modules.setdefault("app.execution.safety_policy", MagicMock())

from app.config.models import Settings, SprintRetryConfig
from app.workflow.sprint_supervisor import SprintSupervisor, SprintResult


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temp workspace."""
    ws_root = tmp_path / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)
    return ws_root


@pytest.fixture
def workspace_manager(tmp_workspace):
    """Create a WorkspaceManager."""
    from app.workspace.manager import WorkspaceManager
    ws = WorkspaceManager()
    ws.workspace_root = tmp_workspace
    return ws


@pytest.fixture
def mock_llm_manager():
    """Create a mock LLMManager."""
    return MagicMock()


@pytest.fixture
def settings_with_retries():
    """Create Settings with retry limits."""
    return Settings(
        sprint_retry=SprintRetryConfig(
            max_dev_review_iterations=3,
            max_qa_iterations=3,
            max_spec_fix_iterations=2,
        )
    )


# ===========================================================================
# Tests
# ===========================================================================

class TestSprintSupervisorInstantiation:
    """Test SprintSupervisor instantiation and structure."""

    def test_sprint_supervisor_instantiates(
        self,
        workspace_manager,
        mock_llm_manager,
        settings_with_retries,
    ):
        """Test: SprintSupervisor can be instantiated."""
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings_with_retries,
        )
        assert supervisor is not None
        assert supervisor.workspace_manager is workspace_manager
        assert supervisor.llm_manager is mock_llm_manager

    def test_sprint_supervisor_default_settings(
        self,
        workspace_manager,
        mock_llm_manager,
    ):
        """Test: SprintSupervisor uses defaults when settings.sprint_retry is None."""
        settings = Settings()  # No sprint_retry config
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings,
        )
        # Should use fallback defaults.
        assert supervisor._max_dev_review_iterations == 3
        assert supervisor._max_qa_iterations == 3
        assert supervisor._max_spec_fix_iterations == 2

    def test_sprint_supervisor_custom_retry_limits(
        self,
        workspace_manager,
        mock_llm_manager,
    ):
        """Test: SprintSupervisor respects custom retry limits."""
        settings = Settings(
            sprint_retry=SprintRetryConfig(
                max_dev_review_iterations=5,
                max_qa_iterations=4,
                max_spec_fix_iterations=3,
            )
        )
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings,
        )
        assert supervisor._max_dev_review_iterations == 5
        assert supervisor._max_qa_iterations == 4
        assert supervisor._max_spec_fix_iterations == 3

    def test_sprint_result_success(self):
        """Test: SprintResult(success=True)."""
        result = SprintResult(success=True)
        assert result.success is True
        assert result.blocked is False
        assert result.message == ""

    def test_sprint_result_blocked(self):
        """Test: SprintResult(success=False, blocked=True)."""
        result = SprintResult(
            success=False,
            blocked=True,
            message="Max retries exceeded",
        )
        assert result.success is False
        assert result.blocked is True
        assert result.message == "Max retries exceeded"

    def test_sprint_result_error(self):
        """Test: SprintResult(success=False, blocked=False)."""
        result = SprintResult(
            success=False,
            blocked=False,
            message="Unexpected error",
        )
        assert result.success is False
        assert result.blocked is False
        assert result.message == "Unexpected error"

    def test_sprint_supervisor_has_agent_factory(
        self,
        workspace_manager,
        mock_llm_manager,
        settings_with_retries,
    ):
        """Test: SprintSupervisor has agent_factory."""
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings_with_retries,
        )
        assert supervisor.agent_factory is not None
        # Should be able to create agents.
        assert supervisor.agent_factory.create("scrum_master") is not None

    def test_sprint_supervisor_has_run_sprint_method(
        self,
        workspace_manager,
        mock_llm_manager,
        settings_with_retries,
    ):
        """Test: SprintSupervisor has run_sprint method."""
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings_with_retries,
        )
        assert hasattr(supervisor, "run_sprint")
        assert callable(supervisor.run_sprint)

    def test_sprint_supervisor_run_sprint_returns_sprint_result(
        self,
        workspace_manager,
        mock_llm_manager,
        settings_with_retries,
    ):
        """Test: run_sprint returns SprintResult even on error."""
        supervisor = SprintSupervisor(
            workspace_manager=workspace_manager,
            llm_manager=mock_llm_manager,
            settings=settings_with_retries,
        )
        # Set up minimal workspace.
        proj_id = "test"
        workspace_manager.create_workspace(proj_id)

        # run_sprint should catch exceptions and return SprintResult.
        result = supervisor.run_sprint(
            project_id=proj_id,
            sprint_number=1,
            request="test",
        )
        assert isinstance(result, SprintResult)
        # It will fail because we have no real artifacts, but should return properly.
        assert result.success is False

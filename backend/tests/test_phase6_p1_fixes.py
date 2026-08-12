"""test_phase6_p1_fixes.py — Phase 6 P1 blocker regression tests.

P1-A: MAX_PROJECTS_PER_KEY per-owner project count enforcement in api/project.py
P1-B: Celery worker entrypoint — module-level celery_app in pipeline_task.py

Running:
    cd backend
    python -m pytest tests/test_phase6_p1_fixes.py -v
"""
from __future__ import annotations

import os
import sys
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Generator

import pytest

# ============================================================
# Helpers — keep FastAPI dependency injection out of these unit tests
# ============================================================

def _make_project(project_id: str, owner_id: str):
    """Return a minimal project-like object with the attributes the code reads."""
    p = MagicMock()
    p.project_id = project_id
    p.owner_id = owner_id
    p.name = f"project-{project_id}"
    p.description = ""
    p.status = "pending"
    p.current_stage = MagicMock()
    p.current_stage.value = "init"
    p.created_at = MagicMock()
    p.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    return p


def _make_user(user_id: str, role: str = "user"):
    user = MagicMock()
    user.id = user_id
    user.role = role
    return user


def _make_manager(existing_projects: list):
    """Return a minimal ProjectManager mock whose repository.list_by_owner returns existing_projects."""
    repo = MagicMock()
    repo.list_by_owner.return_value = existing_projects
    manager = MagicMock()
    manager.repository = repo
    return manager


# ============================================================
# P1-A: MAX_PROJECTS_PER_KEY enforcement
# ============================================================

class TestMaxProjectsPerKey:
    """Unit tests for _enforce_project_limit() in api/project.py."""

    def _import_enforce(self):
        """Import _enforce_project_limit fresh (clears module cache first)."""
        if "app.api.project" in sys.modules:
            del sys.modules["app.api.project"]
        from app.api.project import _enforce_project_limit
        return _enforce_project_limit

    def test_below_limit_succeeds(self, monkeypatch):
        """Creating the Nth project succeeds when N < MAX_PROJECTS_PER_KEY."""
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "5")
        enforce = self._import_enforce()

        existing = [_make_project(str(i), "u1") for i in range(4)]   # 4 < 5
        manager = _make_manager(existing)
        # Must not raise
        enforce(manager, "u1")
        manager.repository.list_by_owner.assert_called_once_with("u1")

    def test_at_limit_is_rejected(self, monkeypatch):
        """Creating when count == limit must raise HTTP 429."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "3")
        enforce = self._import_enforce()

        existing = [_make_project(str(i), "u1") for i in range(3)]   # 3 == limit
        manager = _make_manager(existing)
        with pytest.raises(HTTPException) as exc_info:
            enforce(manager, "u1")
        assert exc_info.value.status_code == 429

    def test_above_limit_is_rejected(self, monkeypatch):
        """Creating when count > limit must raise HTTP 429."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "2")
        enforce = self._import_enforce()

        existing = [_make_project(str(i), "u1") for i in range(5)]   # 5 > 2
        manager = _make_manager(existing)
        with pytest.raises(HTTPException) as exc_info:
            enforce(manager, "u1")
        assert exc_info.value.status_code == 429

    def test_different_users_have_independent_counts(self, monkeypatch):
        """User-A at limit does not block User-B."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "2")
        enforce = self._import_enforce()

        # User A has 2 projects (at limit)
        repo = MagicMock()
        repo.list_by_owner.side_effect = lambda uid: (
            [_make_project("a1", "userA"), _make_project("a2", "userA")] if uid == "userA"
            else []
        )
        manager = MagicMock()
        manager.repository = repo

        # User A is rejected
        with pytest.raises(HTTPException):
            enforce(manager, "userA")

        # User B is accepted (0 projects)
        enforce(manager, "userB")   # must not raise

    def test_error_message_contains_limit(self, monkeypatch):
        """HTTP 429 detail must mention the configured limit value."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "7")
        enforce = self._import_enforce()

        existing = [_make_project(str(i), "u1") for i in range(7)]
        manager = _make_manager(existing)
        with pytest.raises(HTTPException) as exc_info:
            enforce(manager, "u1")
        assert "7" in exc_info.value.detail

    def test_env_var_limit_respected(self, monkeypatch):
        """MAX_PROJECTS_PER_KEY env var controls the actual limit."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "10")
        enforce = self._import_enforce()

        # 9 projects — below the configured limit of 10
        existing = [_make_project(str(i), "u1") for i in range(9)]
        manager = _make_manager(existing)
        enforce(manager, "u1")   # must not raise

        # 10 projects — at the configured limit of 10
        existing_at = [_make_project(str(i), "u1") for i in range(10)]
        manager_at = _make_manager(existing_at)
        with pytest.raises(HTTPException) as exc_info:
            enforce(manager_at, "u1")
        assert exc_info.value.status_code == 429

    def test_anonymous_user_counted_independently(self, monkeypatch):
        """'anonymous' user_id (AUTH_ENABLED=false) has its own project count."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "1")
        enforce = self._import_enforce()

        existing = [_make_project("anon-p1", "anonymous")]
        manager = _make_manager(existing)
        with pytest.raises(HTTPException) as exc_info:
            enforce(manager, "anonymous")
        assert exc_info.value.status_code == 429

    def test_zero_projects_always_passes(self, monkeypatch):
        """A user with 0 projects must never be blocked (limit >= 1 guaranteed)."""
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "1")
        enforce = self._import_enforce()

        manager = _make_manager([])
        enforce(manager, "u1")   # must not raise

    def test_existing_validation_unchanged(self, monkeypatch):
        """_validate_project_request still rejects an empty name regardless of limit."""
        from fastapi import HTTPException
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "100")
        if "app.api.project" in sys.modules:
            del sys.modules["app.api.project"]
        from app.api.project import _validate_project_request

        req = MagicMock()
        req.name = ""
        req.description = ""
        with pytest.raises(HTTPException) as exc_info:
            _validate_project_request(req)
        assert exc_info.value.status_code == 422

    def test_max_projects_per_key_constant_is_module_level(self, monkeypatch):
        """MAX_PROJECTS_PER_KEY must be a module-level int, not a constant literal."""
        monkeypatch.setenv("MAX_PROJECTS_PER_KEY", "42")
        if "app.api.project" in sys.modules:
            del sys.modules["app.api.project"]
        from app.api.project import MAX_PROJECTS_PER_KEY
        assert isinstance(MAX_PROJECTS_PER_KEY, int)
        assert MAX_PROJECTS_PER_KEY == 42


# ============================================================
# P1-B: Celery worker entrypoint
# ============================================================

class TestCeleryEagerTaskRegistration:
    """Regression tests for P0 — run_pipeline must be registered at module import.

    A Celery worker imports the module, then blocks on the broker queue.
    It never calls dispatch_pipeline(), so lazy registration means zero tasks.
    The fix: _task_fn = _define_celery_task(celery_app) runs at module level
    when celery_app is not None.
    """

    def test_task_fn_is_none_without_broker(self, monkeypatch):
        """Without a broker, _task_fn must be None (Celery disabled path)."""
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt
        assert pt._task_fn is None

    def test_task_fn_registered_without_calling_dispatch_pipeline(self, monkeypatch):
        """When broker is set and celery installed, _task_fn must be set at import
        WITHOUT dispatch_pipeline() ever being called — this is the P0 fix."""
        try:
            import celery as _c
        except ImportError:
            pytest.skip("celery not installed in test environment")

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/99")
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/99")
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]

        # Import module — do NOT call dispatch_pipeline()
        import app.tasks.pipeline_task as pt

        # _task_fn must already be set at module level
        assert pt._task_fn is not None, (
            "_task_fn is None after module import — P0 regression: run_pipeline "
            "is not registered until dispatch_pipeline() is called, so the Celery "
            "worker starts with zero tasks."
        )

    def test_task_fn_is_named_run_pipeline(self, monkeypatch):
        """The registered task must have the canonical name aidevos.run_pipeline."""
        try:
            import celery as _c
        except ImportError:
            pytest.skip("celery not installed in test environment")

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/99")
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/99")
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt

        assert pt._task_fn is not None
        assert pt._task_fn.name == "aidevos.run_pipeline", (
            f"Expected task name 'aidevos.run_pipeline', got {pt._task_fn.name!r}"
        )

    def test_get_task_returns_already_registered_task(self, monkeypatch):
        """_get_task() must return the module-level _task_fn, not re-register it."""
        try:
            import celery as _c
        except ImportError:
            pytest.skip("celery not installed in test environment")

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/99")
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/99")
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt

        # _task_fn already set at module level; _get_task() must return same object
        expected = pt._task_fn
        assert pt._get_task() is expected

    def test_define_celery_task_not_called_lazily(self, monkeypatch):
        """Verify _define_celery_task is NOT the only registration path.

        Before the P0 fix, _define_celery_task was only called from _get_task()
        which was only called from dispatch_pipeline(). After the fix, it is also
        called eagerly. This test confirms the lazy path still works as a fallback
        (e.g. if celery_app becomes non-None after module import for some reason).
        """
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt
        # Without broker: _task_fn is None, _get_task() returns None
        assert pt._task_fn is None
        assert pt._get_task() is None

        # Simulate a late-arriving app (should not happen in production)
        fake_task = MagicMock()
        with patch.object(pt, "celery_app", MagicMock()):
            with patch.object(pt, "_define_celery_task", return_value=fake_task):
                result = pt._get_task()
        assert result is fake_task


class TestCeleryWorkerEntrypoint:
    """Unit tests for the module-level celery_app in tasks/pipeline_task.py."""

    def _reload_pipeline_task(self, broker_url: str | None = None, install_celery: bool = True):
        """Reload pipeline_task with a controlled environment."""
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key or key == "celery":
                del sys.modules[key]

        env_patch = {}
        if broker_url is not None:
            env_patch["CELERY_BROKER_URL"] = broker_url
            env_patch["CELERY_RESULT_BACKEND"] = broker_url
        else:
            env_patch.pop("CELERY_BROKER_URL", None)

        with patch.dict(os.environ, env_patch, clear=False):
            # Remove broker URL when None so the module sees it as absent
            if broker_url is None:
                os.environ.pop("CELERY_BROKER_URL", None)
                os.environ.pop("CELERY_RESULT_BACKEND", None)

            if install_celery:
                # Ensure celery is importable (it is in the test environment)
                import app.tasks.pipeline_task as pt
            else:
                # Simulate celery not installed
                with patch.dict(sys.modules, {"celery": None}):
                    import app.tasks.pipeline_task as pt
            return pt

    def test_celery_app_attribute_exists_at_module_level(self):
        """pipeline_task must expose a module-level 'celery_app' attribute."""
        import app.tasks.pipeline_task as pt
        assert hasattr(pt, "celery_app"), (
            "pipeline_task must expose a module-level 'celery_app' attribute "
            "so `celery -A app.tasks.pipeline_task worker` can discover it"
        )

    def test_celery_app_is_none_without_broker(self, monkeypatch):
        """celery_app must be None when CELERY_BROKER_URL is not set."""
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)

        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt
        assert pt.celery_app is None

    def test_get_celery_app_returns_same_as_module_attr(self, monkeypatch):
        """_get_celery_app() must return the same object as module-level celery_app."""
        import app.tasks.pipeline_task as pt
        assert pt._get_celery_app() is pt.celery_app

    def test_celery_app_is_celery_instance_when_broker_set(self, monkeypatch):
        """When CELERY_BROKER_URL is set and celery is installed, celery_app must be a Celery instance."""
        try:
            import celery as _celery_pkg
        except ImportError:
            pytest.skip("celery not installed in test environment")

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/99")
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/99")

        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt

        assert pt.celery_app is not None
        assert isinstance(pt.celery_app, _celery_pkg.Celery)

    def test_dispatch_pipeline_uses_celery_app_when_available(self, monkeypatch):
        """dispatch_pipeline must use the module-level celery_app (via _get_task)."""
        import app.tasks.pipeline_task as pt

        mock_task = MagicMock()
        mock_task.apply_async.return_value = None

        with patch.object(pt, "_get_task", return_value=mock_task):
            pt.dispatch_pipeline(MagicMock(), "proj-123", "request", skip_qa=False)
        mock_task.apply_async.assert_called_once()

    def test_dispatch_pipeline_falls_back_to_threads_without_broker(self, monkeypatch):
        """dispatch_pipeline must use threading when celery_app is None."""
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt
        assert pt.celery_app is None

        mock_manager = MagicMock()
        with patch.object(pt, "_run_in_thread") as mock_thread:
            pt.dispatch_pipeline(mock_manager, "proj-456", "req")
        mock_thread.assert_called_once()

    def test_celery_app_configured_with_json_serializer(self, monkeypatch):
        """The Celery app must be configured with JSON serializer for security."""
        try:
            import celery as _celery_pkg
        except ImportError:
            pytest.skip("celery not installed in test environment")

        monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/99")
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/99")

        for key in list(sys.modules.keys()):
            if "pipeline_task" in key:
                del sys.modules[key]
        import app.tasks.pipeline_task as pt

        assert pt.celery_app is not None
        conf = pt.celery_app.conf
        assert conf.task_serializer == "json"
        assert "json" in conf.accept_content

    def test_docker_compose_worker_command_is_correct(self):
        """docker-compose.yml worker command must use module path, not a function attribute."""
        compose_path = (
            Path(__file__).resolve().parents[1] / "docker-compose.yml"
        )
        assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"
        content = compose_path.read_text()
        # Must NOT reference _get_celery_app (a function)
        assert "_get_celery_app" not in content, (
            "docker-compose.yml still references _get_celery_app. "
            "Celery -A needs a module path, not a function attribute."
        )
        # Must reference the correct module
        assert "app.tasks.pipeline_task" in content, (
            "docker-compose.yml must reference app.tasks.pipeline_task as the Celery -A target"
        )

"""test_phase6_celery_dispatch.py — Phase 6 Task 1: Celery dispatch replaces daemon threads.

Verifies:
  1. launch_pipeline_background() with is_stage=False calls dispatch_pipeline()
     instead of spawning a threading.Thread directly.
  2. launch_pipeline_background() with is_stage=True still uses threading (no
     Celery task exists for stage-level runs) and calls manager.run_stage().
  3. dispatch_pipeline() falls back to threading when CELERY_BROKER_URL is unset.
  4. dispatch_pipeline() uses Celery (apply_async) when a broker URL is configured.
  5. The threading fallback in dispatch_pipeline() calls manager.run() correctly.

Running:
    cd backend
    python -m pytest tests/test_phase6_celery_dispatch.py -v
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# 1-2: launch_pipeline_background() routing
# ---------------------------------------------------------------------------

class TestLaunchPipelineBackground:
    """Unit tests for the routing logic inside launch_pipeline_background()."""

    def _import(self):
        from app.api.workflow import launch_pipeline_background
        return launch_pipeline_background

    def test_non_stage_run_calls_dispatch_pipeline(self):
        """is_stage=False must delegate to dispatch_pipeline(), not spawn a bare thread."""
        launch = self._import()
        manager = MagicMock()

        with patch("app.api.workflow.dispatch_pipeline") as mock_dispatch:
            launch(manager, "proj-1", req="build a todo app", skip_qa=False, is_stage=False)

        mock_dispatch.assert_called_once_with(manager, "proj-1", "build a todo app", False)

    def test_non_stage_run_passes_skip_qa(self):
        """skip_qa=True must be forwarded to dispatch_pipeline()."""
        launch = self._import()
        manager = MagicMock()

        with patch("app.api.workflow.dispatch_pipeline") as mock_dispatch:
            launch(manager, "proj-2", req="app", skip_qa=True, is_stage=False)

        mock_dispatch.assert_called_once_with(manager, "proj-2", "app", True)

    def test_non_stage_run_does_not_spawn_a_thread(self):
        """is_stage=False must NOT create a threading.Thread in workflow.py itself."""
        launch = self._import()
        manager = MagicMock()

        with patch("app.api.workflow.dispatch_pipeline"):
            with patch("app.api.workflow.threading.Thread") as mock_thread:
                launch(manager, "proj-3", req="app", is_stage=False)

        mock_thread.assert_not_called()

    def test_stage_run_calls_manager_run_stage(self):
        """is_stage=True must call manager.run_stage() (via thread)."""
        launch = self._import()
        manager = MagicMock()
        called = threading.Event()

        def _fake_run_stage(project_id, stage_name, comment_text):
            called.set()

        manager.run_stage.side_effect = _fake_run_stage

        launch(manager, "proj-4", is_stage=True, stage_name="architect", comment_text="feedback")

        called.wait(timeout=3)
        manager.run_stage.assert_called_once_with("proj-4", "architect", "feedback")

    def test_stage_run_does_not_call_dispatch_pipeline(self):
        """is_stage=True must NOT call dispatch_pipeline()."""
        launch = self._import()
        manager = MagicMock()

        with patch("app.api.workflow.dispatch_pipeline") as mock_dispatch:
            # Stage run spawns a real thread; we block briefly so run_stage is called
            manager.run_stage.return_value = None
            launch(manager, "proj-5", is_stage=True, stage_name="designer", comment_text="")
            time.sleep(0.05)

        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# 3-5: dispatch_pipeline() itself
# ---------------------------------------------------------------------------

class TestDispatchPipeline:
    """Unit tests for the dispatch_pipeline() public API in pipeline_task.py."""

    def test_falls_back_to_thread_when_no_broker_url(self):
        """When CELERY_BROKER_URL is unset, dispatch_pipeline must use threading."""
        from app.tasks.pipeline_task import dispatch_pipeline

        manager = MagicMock()
        ran = threading.Event()
        manager.run.side_effect = lambda *a, **kw: ran.set()

        # Ensure Celery is not picked up by clearing broker URL
        with patch("app.tasks.pipeline_task._BROKER_URL", ""):
            with patch("app.tasks.pipeline_task._celery_app", None):
                with patch("app.tasks.pipeline_task._task_fn", None):
                    dispatch_pipeline(manager, "proj-t", "build a chat app", skip_qa=False)

        ran.wait(timeout=3)
        manager.run.assert_called_once_with("proj-t", "build a chat app", False)

    def test_threading_fallback_thread_is_daemon(self):
        """The fallback thread must be a daemon thread (no process hang on exit)."""
        from app.tasks.pipeline_task import _run_in_thread

        manager = MagicMock()
        manager.run.return_value = None

        spawned_threads = []
        original_thread_cls = threading.Thread

        def _capture_thread(*args, **kwargs):
            t = original_thread_cls(*args, **kwargs)
            spawned_threads.append(t)
            return t

        with patch("app.tasks.pipeline_task.threading.Thread", side_effect=_capture_thread):
            _run_in_thread(manager, "proj-d", "request")

        assert len(spawned_threads) == 1
        assert spawned_threads[0].daemon is True

    def test_threading_fallback_calls_manager_run_with_skip_qa(self):
        """_run_in_thread() must forward skip_qa to manager.run()."""
        from app.tasks.pipeline_task import _run_in_thread

        manager = MagicMock()
        done = threading.Event()
        manager.run.side_effect = lambda *a, **kw: done.set()

        _run_in_thread(manager, "proj-q", "build a blog", skip_qa=True)

        done.wait(timeout=3)
        manager.run.assert_called_once_with("proj-q", "build a blog", True)

    def test_celery_apply_async_called_when_task_available(self):
        """When a Celery task is available, dispatch_pipeline must call apply_async."""
        from app.tasks.pipeline_task import dispatch_pipeline

        manager = MagicMock()
        mock_task = MagicMock()

        with patch("app.tasks.pipeline_task._get_task", return_value=mock_task):
            dispatch_pipeline(manager, "proj-c", "celery request", skip_qa=False)

        mock_task.apply_async.assert_called_once_with(
            args=["proj-c", "celery request", False],
            task_id="pipeline-proj-c",
        )

    def test_celery_failure_falls_back_to_thread(self):
        """If apply_async raises, dispatch_pipeline must fall back to threading."""
        from app.tasks.pipeline_task import dispatch_pipeline

        manager = MagicMock()
        done = threading.Event()
        manager.run.side_effect = lambda *a, **kw: done.set()

        mock_task = MagicMock()
        mock_task.apply_async.side_effect = Exception("Redis down")

        with patch("app.tasks.pipeline_task._get_task", return_value=mock_task):
            dispatch_pipeline(manager, "proj-fb", "request")

        done.wait(timeout=3)
        manager.run.assert_called_once()

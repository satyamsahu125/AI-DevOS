"""pipeline_task.py — Celery task for AI DevOS pipeline execution.

Replaces the daemon thread pattern in api/workflow.py:
    threading.Thread(target=_run, daemon=True, name=f"workflow-{project_id}").start()

With a serializable, cancellable, isolated Celery task:
    run_pipeline.delay(project_id, request)

Celery requires Redis as a message broker. When Redis is unavailable
(dev environments without Docker), this module falls back to the existing
threading approach so the system keeps working.

Configuration:
    CELERY_BROKER_URL=redis://localhost:6379/0      # default when Redis is present
    CELERY_RESULT_BACKEND=redis://localhost:6379/0  # optional — for result inspection

When CELERY_BROKER_URL is not set, Celery is disabled and the fallback
`run_pipeline_threaded()` function handles background execution instead.

Usage (from api/workflow.py):
    from ..tasks.pipeline_task import dispatch_pipeline
    dispatch_pipeline(manager, project_id, request)
    # dispatch_pipeline() chooses Celery vs threading based on availability
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "")
_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", _BROKER_URL)

# --------------------------------------------------------------------------
# Celery app setup (lazy — only built when Redis is configured)
# --------------------------------------------------------------------------

_celery_app: Any = None


def _get_celery_app():
    """Return the Celery app singleton, creating it if needed.

    Returns None when CELERY_BROKER_URL is not set or Celery is not installed.
    """
    global _celery_app
    if _celery_app is not None:
        return _celery_app

    if not _BROKER_URL:
        logger.debug("[pipeline_task] CELERY_BROKER_URL not set — Celery disabled, using threads")
        return None

    try:
        from celery import Celery  # type: ignore[import]
        app = Celery(
            "aidevos",
            broker=_BROKER_URL,
            backend=_RESULT_BACKEND or None,
        )
        app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            task_track_started=True,
            task_acks_late=True,          # re-queue if worker crashes
            worker_prefetch_multiplier=1,  # one pipeline per worker slot
        )
        _celery_app = app
        logger.info("[pipeline_task] Celery configured: broker=%s", _BROKER_URL)
        return app
    except ImportError:
        logger.warning("[pipeline_task] celery not installed — falling back to threads")
        return None


# --------------------------------------------------------------------------
# The Celery task
# --------------------------------------------------------------------------

def _define_celery_task(app):
    """Define and register the run_pipeline task on the Celery app.

    Called lazily so the task is only registered when Celery is available.
    """
    @app.task(
        name="aidevos.run_pipeline",
        bind=True,
        max_retries=0,
        track_started=True,
    )
    def run_pipeline(self, project_id: str, request: str, skip_qa: bool = False) -> dict:
        """Execute the full pipeline for project_id as a Celery task.

        Each project_id gets exactly one task running at a time (enforced by
        Celery's task deduplication via the project_id in the task ID). If a
        second request arrives while a task is running, it reuses the existing one.

        Returns the WorkflowResult dict for inspection via AsyncResult.
        """
        log = logger.getChild(f"task.{project_id[:8]}")
        log.info("pipeline task started: project_id=%s", project_id)
        try:
            from ..kernel.container import container
            manager = container.workflow_manager
            result = manager.run(project_id, request, skip_qa)
            log.info("pipeline task completed: project_id=%s success=%s", project_id, result.success if hasattr(result, "success") else "?")
            if hasattr(result, "model_dump"):
                return result.model_dump()
            if hasattr(result, "__dict__"):
                return {k: str(v) for k, v in result.__dict__.items()}
            return {"project_id": project_id, "success": True}
        except Exception as exc:
            log.error("pipeline task failed: project_id=%s error=%s", project_id, exc, exc_info=True)
            raise

    return run_pipeline


_task_fn = None


def _get_task():
    """Return the registered Celery task function, or None if Celery is unavailable."""
    global _task_fn
    if _task_fn is not None:
        return _task_fn
    app = _get_celery_app()
    if app is None:
        return None
    _task_fn = _define_celery_task(app)
    return _task_fn


# --------------------------------------------------------------------------
# Public dispatch API
# --------------------------------------------------------------------------

def dispatch_pipeline(
    manager: Any,
    project_id: str,
    request: str,
    skip_qa: bool = False,
) -> None:
    """Dispatch a pipeline run — uses Celery if available, threads otherwise.

    This is the single call site for launching pipeline execution in the background.
    api/workflow.py should call this instead of creating threading.Thread directly.

    Parameters
    ----------
    manager:
        WorkflowManager instance (used by the threading path only — Celery
        resolves it from the container independently).
    project_id:
        Project to run.
    request:
        User request / description.
    skip_qa:
        Skip the QA clarification phase.
    """
    task = _get_task()
    if task is not None:
        try:
            task.apply_async(
                args=[project_id, request, skip_qa],
                task_id=f"pipeline-{project_id}",  # idempotent task ID per project
            )
            logger.info("[pipeline_task] dispatched via Celery: project_id=%s", project_id)
            return
        except Exception as exc:
            logger.warning(
                "[pipeline_task] Celery dispatch failed (%s), falling back to threads",
                exc,
            )

    # Threading fallback
    _run_in_thread(manager, project_id, request, skip_qa)


def _run_in_thread(manager: Any, project_id: str, request: str, skip_qa: bool = False) -> None:
    """Run pipeline in a daemon thread (fallback when Celery is unavailable)."""
    def _run():
        try:
            manager.run(project_id, request, skip_qa)
        except Exception as exc:
            logger.error(
                "[pipeline_task] pipeline crashed in thread: project_id=%s error=%s",
                project_id, exc,
                exc_info=True,
            )

    thread = threading.Thread(target=_run, daemon=True, name=f"workflow-{project_id}")
    thread.start()
    logger.info("[pipeline_task] dispatched via thread: project_id=%s thread=%s", project_id, thread.name)

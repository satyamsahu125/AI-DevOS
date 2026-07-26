from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from ..api.websocket import ws_manager

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Broadcasts pipeline events to connected WebSocket clients.

    Called by WorkflowEngine, WorkflowManager, and agents at key moments in the pipeline.

    All methods are sync-safe — they schedule the async broadcast on the event loop without
    blocking the pipeline thread.

    Thread-safety: FastAPI runs sync BackgroundTasks in a threadpool executor — those threads
    have NO asyncio event loop of their own. `asyncio.get_running_loop()` raises RuntimeError
    in those threads, so we must capture the uvicorn event loop at startup and schedule
    coroutines onto it via `loop.call_soon_threadsafe`.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the running event loop at app startup for use in background threads.

        Call this once from an async lifespan / startup hook, e.g.:
            broadcaster.bind_loop(asyncio.get_running_loop())
        """
        self._loop = loop
        logger.debug("EventBroadcaster bound to event loop %s", loop)

    def _send(self, project_id: str, message: dict) -> None:
        """Schedule async broadcast from any thread (sync-safe)."""
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

        loop = self._loop
        if loop is None:
            # Fallback: try to grab a running loop (works when called directly from
            # async context, e.g. tests or startup code before bind_loop is called).
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.debug("EventBroadcaster: no loop bound and no running loop — dropping: %s", message.get("type"))
                return

        async def _do_broadcast() -> None:
            await ws_manager.broadcast(project_id, message)

        # call_soon_threadsafe is the ONLY safe way to schedule a coroutine onto an
        # event loop from a non-async thread.  ensure_future / create_task must be
        # called from within the loop thread.
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(_do_broadcast(), loop=loop)
        )

    def stage_started(self, project_id: str, stage: str, attempt: int = 1) -> None:
        self._send(
            project_id,
            {
                "type": "stage_started",
                "stage": stage,
                "attempt": attempt,
                "message": f"Starting {stage.replace('_', ' ')}...",
            },
        )
        logger.debug("Broadcast stage_started: %s", stage)

    def stage_complete(
        self,
        project_id: str,
        stage: str,
        attempt: int,
        duration_seconds: float = 0,
    ) -> None:
        self._send(
            project_id,
            {
                "type": "stage_complete",
                "stage": stage,
                "attempt": attempt,
                "duration_seconds": round(duration_seconds, 1),
                "message": f"{stage.replace('_', ' ').title()} completed on attempt {attempt}",
            },
        )

    def stage_failed(self, project_id: str, stage: str, reason: str) -> None:
        self._send(
            project_id,
            {
                "type": "stage_failed",
                "stage": stage,
                "reason": reason,
                "message": f"{stage} failed: {reason[:100]}",
            },
        )

    def stage_retry(
        self, project_id: str, stage: str, attempt: int, feedback: str
    ) -> None:
        self._send(
            project_id,
            {
                "type": "stage_retry",
                "stage": stage,
                "attempt": attempt,
                "feedback": feedback[:200],
                "message": f"Retrying {stage} (attempt {attempt}) with feedback",
            },
        )

    def log_line(
        self, project_id: str, stage: str, line: str, level: str = "info"
    ) -> None:
        self._send(
            project_id,
            {
                "type": "log_line",
                "stage": stage,
                "line": line,
                "level": level,
            },
        )

    def file_added(
        self, project_id: str, file_path: str, stage: str, size_bytes: int = 0
    ) -> None:
        self._send(
            project_id,
            {
                "type": "file_added",
                "file_path": file_path,
                "stage": stage,
                "size_bytes": size_bytes,
                "message": f"Generated: {file_path}",
            },
        )

    def status_update(
        self,
        project_id: str,
        state: str,
        current_stage: str | None = None,
        stages_completed: list[str] | None = None,
    ) -> None:
        self._send(
            project_id,
            {
                "type": "status_update",
                "state": state,
                "current_stage": current_stage,
                "stages_completed": stages_completed or [],
            },
        )

    def qa_question(
        self, project_id: str, question: str, index: int, total: int
    ) -> None:
        self._send(
            project_id,
            {
                "type": "qa_question",
                "question": question,
                "index": index,
                "total": total,
                "message": f"Q&A: question {index + 1} of {total}",
            },
        )

    def approval_needed(self, project_id: str, stage: str, preview: str) -> None:
        self._send(
            project_id,
            {
                "type": "approval_needed",
                "stage": stage,
                "preview": preview[:300],
                "message": f"Waiting for approval: {stage}",
            },
        )

    def change_analyzed(
        self, project_id: str, affected_stages: list[str], safe_stages: list[str]
    ) -> None:
        self._send(
            project_id,
            {
                "type": "change_analyzed",
                "affected_stages": affected_stages,
                "safe_stages": safe_stages,
                "message": f"Impact: {len(affected_stages)} stages will re-run",
            },
        )

    def pipeline_done(
        self,
        project_id: str,
        stages_completed: list[str],
        duration_seconds: float = 0,
    ) -> None:
        self._send(
            project_id,
            {
                "type": "pipeline_done",
                "stages_completed": stages_completed,
                "total_stages": len(stages_completed),
                "duration_seconds": round(duration_seconds, 1),
                "message": "Pipeline complete!",
            },
        )


# Singleton
broadcaster = EventBroadcaster()

from __future__ import annotations

from threading import Lock


class ExecutionStateRegistry:
    """Tracks, per project_id, whether a pipeline/stage call is actually executing right now in
    this process, and whether a stop has been requested for it.

    Purely in-memory and process-local -- the pipeline itself runs synchronously within this
    same process, so "is it running" and "should it stop" only ever need to be known here, not
    persisted. (Persisted pipeline *progress* still lives in workspace project.json, separately.)
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._running: set[str] = set()
        self._stop_requested: set[str] = set()

    def mark_running(self, project_id: str) -> None:
        """Mark project_id as actively executing, clearing any stale stop request left over
        from a previous run (a fresh run should never be born already-stopped)."""
        with self._lock:
            self._running.add(project_id)
            self._stop_requested.discard(project_id)

    def mark_stopped(self, project_id: str) -> None:
        """Mark project_id as no longer executing (call in a finally: block)."""
        with self._lock:
            self._running.discard(project_id)

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._running

    def request_stop(self, project_id: str) -> bool:
        """Flag project_id's in-flight execution to stop at its next checkpoint.
        Returns False (no-op) if nothing is currently running for it."""
        with self._lock:
            if project_id not in self._running:
                return False
            self._stop_requested.add(project_id)
            return True

    def is_stop_requested(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._stop_requested

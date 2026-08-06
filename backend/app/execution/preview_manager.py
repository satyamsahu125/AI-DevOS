"""preview_manager.py — Live subprocess preview of generated apps.

R5: After each backend sprint that passes R2 sandbox verification, starts the
generated FastAPI/Node app in a subprocess and exposes it via a FastAPI reverse
proxy at /preview/{project_id}/. Users can see the live app in a UI iframe.

Design:
- One subprocess per project — old process stopped before new one starts.
- Port pool: 9000–9019 (configurable via _BASE_PORT / _MAX_PREVIEWS).
- Non-fatal: all operations are wrapped in try/except; failures are logged.
- Idle timeout: processes inactive for 30 minutes are stopped automatically.
- Thread-safe: single internal lock guards the _previews dict.

Security:
- Preview processes run as the same OS user as the server (no sandbox isolation).
- Only active when PREVIEW_ENABLED=true (default: false for production).
- Reverse proxy validates project existence before forwarding requests.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_PORT = int(os.getenv("PREVIEW_BASE_PORT", "9000"))
_MAX_PREVIEWS = int(os.getenv("PREVIEW_MAX_SLOTS", "20"))
_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes
_PREVIEW_ENABLED = os.getenv("PREVIEW_ENABLED", "false").lower() in ("true", "1", "yes")


class PreviewManager:
    """Manages per-project subprocess previews of generated apps.

    One preview process per project at a time. Ports are assigned from a
    fixed pool starting at _BASE_PORT. When a project's preview is stopped,
    its port is returned to the pool.

    Parameters
    ----------
    enabled : bool | None
        Override for PREVIEW_ENABLED env var. Useful in tests.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._enabled = enabled if enabled is not None else _PREVIEW_ENABLED
        self._previews: dict[str, dict] = {}  # project_id → {proc, port, stack, last_access}
        self._lock = threading.Lock()
        self._port_registry: set[int] = set()
        # Background thread that cleans up idle previews
        if self._enabled:
            self._start_idle_cleanup_thread()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, project_id: str, project_dir: Path, stack: str) -> int | None:
        """Start the preview subprocess for project_id.

        Stops any existing preview first. Returns the assigned port, or None
        if the preview cannot be started (disabled, no ports, launch failed).
        """
        if not self._enabled:
            logger.debug("[PreviewManager] preview disabled (PREVIEW_ENABLED=false), skipping start")
            return None

        with self._lock:
            # Stop existing preview for this project before starting a new one
            self._stop_locked(project_id)

            port = self._assign_port()
            if port is None:
                logger.warning("[PreviewManager] no available ports (pool exhausted) for %s", project_id)
                return None

            try:
                proc = self._launch(project_dir, stack, port)
                if proc is None:
                    logger.warning("[PreviewManager] could not launch preview for %s (stack=%s)", project_id, stack)
                    return None

                self._previews[project_id] = {
                    "proc": proc,
                    "port": port,
                    "stack": stack,
                    "last_access": time.time(),
                    "project_dir": str(project_dir),
                }
                self._port_registry.add(port)
                logger.info(
                    "[PreviewManager] started preview: project=%s port=%d pid=%d stack=%s",
                    project_id, port, proc.pid, stack,
                )
                return port
            except Exception as exc:
                self._port_registry.discard(port)
                logger.warning("[PreviewManager] start failed for %s: %s", project_id, exc)
                return None

    def stop(self, project_id: str) -> None:
        """Stop the preview process for project_id. No-op if not running."""
        with self._lock:
            self._stop_locked(project_id)

    def health(self, project_id: str) -> dict:
        """Return current preview status for project_id.

        Returns dict with keys: status, port (if running), url.
        status values: "not_running", "disabled", "starting", "running", "crashed"
        """
        if not self._enabled:
            return {"status": "disabled"}

        preview = self._previews.get(project_id)
        if not preview:
            return {"status": "not_running"}

        proc = preview["proc"]
        port = preview["port"]

        if proc.poll() is not None:
            # Process exited
            exit_code = proc.poll()
            return {"status": "crashed", "port": port, "exit_code": exit_code}

        # Update last_access
        preview["last_access"] = time.time()

        if self._port_open(port):
            return {
                "status": "running",
                "port": port,
                "url": f"/preview/{project_id}/",
            }
        return {"status": "starting", "port": port, "url": f"/preview/{project_id}/"}

    def restart(self, project_id: str) -> int | None:
        """Stop and restart the preview for project_id. Returns new port or None."""
        preview = self._previews.get(project_id)
        if not preview:
            return None
        project_dir = Path(preview.get("project_dir", ""))
        stack = preview.get("stack", "unknown")
        if not project_dir.exists():
            return None
        return self.start(project_id, project_dir, stack)

    def get_preview_logs(self, project_id: str, lines: int = 50) -> list[str]:
        """Return last N lines from the preview process stderr."""
        preview = self._previews.get(project_id)
        if not preview:
            return []
        proc = preview["proc"]
        # Attempt non-blocking read from stderr
        try:
            if proc.stderr and proc.stderr.readable():
                import select
                available, _, _ = select.select([proc.stderr], [], [], 0.1)
                if available:
                    raw = proc.stderr.read(8192)
                    return (raw or b"").decode("utf-8", errors="replace").splitlines()[-lines:]
        except Exception:
            pass
        return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _stop_locked(self, project_id: str) -> None:
        """Internal stop — must be called with self._lock held."""
        preview = self._previews.pop(project_id, None)
        if not preview:
            return
        port = preview.get("port")
        if port:
            self._port_registry.discard(port)
        proc = preview.get("proc")
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
            except Exception:
                pass
        logger.info("[PreviewManager] stopped preview: project=%s port=%s", project_id, port)

    def _launch(self, project_dir: Path, stack: str, port: int) -> subprocess.Popen | None:
        """Launch the app subprocess. Returns Popen or None if not launchable."""
        if stack == "python":
            for name in ("main.py", "app.py", "server.py", "run.py"):
                entry = project_dir / name
                if entry.exists():
                    cmd = [
                        "uvicorn",
                        f"{entry.stem}:app",
                        "--host", "0.0.0.0",
                        "--port", str(port),
                        "--log-level", "warning",
                    ]
                    return subprocess.Popen(
                        cmd,
                        cwd=str(project_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
        elif stack == "node":
            pkg = project_dir / "package.json"
            if pkg.exists():
                env = {**os.environ, "PORT": str(port), "HOST": "0.0.0.0"}
                return subprocess.Popen(
                    ["npm", "start"],
                    cwd=str(project_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
        return None

    def _assign_port(self) -> int | None:
        """Find an available port from the pool. Returns None if all ports in use."""
        for offset in range(_MAX_PREVIEWS):
            port = _BASE_PORT + offset
            if port not in self._port_registry and not self._port_open(port):
                return port
        return None

    @staticmethod
    def _port_open(port: int) -> bool:
        """Return True if something is listening on port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _start_idle_cleanup_thread(self) -> None:
        """Start background thread that stops idle previews every 5 minutes."""
        def _cleanup_loop() -> None:
            while True:
                time.sleep(300)  # check every 5 minutes
                try:
                    self._cleanup_idle()
                except Exception as exc:
                    logger.debug("[PreviewManager] idle cleanup error: %s", exc)

        t = threading.Thread(target=_cleanup_loop, daemon=True, name="preview-idle-cleanup")
        t.start()

    def _cleanup_idle(self) -> None:
        """Stop previews that haven't been accessed in _IDLE_TIMEOUT_SECONDS."""
        now = time.time()
        idle_projects = []
        with self._lock:
            for project_id, preview in self._previews.items():
                if now - preview.get("last_access", now) > _IDLE_TIMEOUT_SECONDS:
                    idle_projects.append(project_id)
        for project_id in idle_projects:
            logger.info("[PreviewManager] stopping idle preview: project=%s", project_id)
            self.stop(project_id)

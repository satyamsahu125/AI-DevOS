# Phase R5 — Live App Preview

**Timeline:** Week 5–7  
**Depends on:** R2 (verified code — prevents previewing broken apps) + R3 (Dockerfile available if Docker preview used)  
**Problem:** AI DevOS generates code but shows nothing running. Developers have no way to verify visually that what was generated matches what they described.  
**Outcome:** After each backend sprint, the generated FastAPI app starts in a subprocess and is accessible via an iframe in the UI. After each frontend sprint, the React dev server starts. The UI shows the live app during and after build.

---

## Why This Matters

This is one of Emergent's most compelling features: you describe an app, watch it being built in real time, and a live preview appears as each component completes. The visual confirmation loop massively reduces the number of revision cycles because users catch misunderstandings immediately rather than after the full pipeline completes.

R2 ensures the code actually runs before we try to preview it. Without R2, the preview would show a crashed or errored app most of the time, which is worse than no preview.

---

## New Module: PreviewManager

**File:** `backend/app/execution/preview_manager.py`

```python
import subprocess
import socket
import time
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_BASE_PORT = 9000
_MAX_PREVIEWS = 20
_IDLE_TIMEOUT_SECONDS = 1800  # 30 minutes


class PreviewManager:
    """Manages per-project subprocess previews of generated apps.
    
    One preview process per project at a time.
    Port assignment: _BASE_PORT + (project_index % _MAX_PREVIEWS)
    Non-fatal: all operations are wrapped in try/except.
    """

    def __init__(self) -> None:
        self._previews: dict[str, dict] = {}  # project_id → {proc, port, last_access}
        self._lock = Lock()
        self._port_registry: set[int] = set()

    def start(self, project_id: str, project_dir: Path, stack: str) -> int | None:
        """Start the preview for project_id. Returns port or None on failure."""
        with self._lock:
            self.stop(project_id)  # Stop any existing preview for this project
            port = self._assign_port()
            if port is None:
                logger.warning("[PreviewManager] no available ports for %s", project_id)
                return None
            try:
                proc = self._launch(project_dir, stack, port)
                if proc is None:
                    return None
                self._previews[project_id] = {
                    "proc": proc,
                    "port": port,
                    "stack": stack,
                    "last_access": time.time(),
                }
                self._port_registry.add(port)
                logger.info("[PreviewManager] started %s on port %d (pid %d)", project_id, port, proc.pid)
                return port
            except Exception as exc:
                logger.warning("[PreviewManager] start failed for %s: %s", project_id, exc)
                return None

    def stop(self, project_id: str) -> None:
        """Stop the preview process for project_id."""
        preview = self._previews.pop(project_id, None)
        if preview:
            port = preview["port"]
            self._port_registry.discard(port)
            try:
                preview["proc"].terminate()
                preview["proc"].wait(timeout=5)
            except Exception:
                try:
                    preview["proc"].kill()
                except Exception:
                    pass
            logger.info("[PreviewManager] stopped %s (port %d)", project_id, port)

    def health(self, project_id: str) -> dict:
        """Check if preview process is running and port is responding."""
        preview = self._previews.get(project_id)
        if not preview:
            return {"status": "not_running"}
        proc = preview["proc"]
        if proc.poll() is not None:
            return {"status": "crashed", "exit_code": proc.poll()}
        port = preview["port"]
        if self._port_open(port):
            return {"status": "running", "port": port}
        return {"status": "starting", "port": port}

    def _launch(self, project_dir: Path, stack: str, port: int) -> subprocess.Popen | None:
        if stack == "python":
            # Find entry point
            for name in ("main.py", "app.py", "server.py"):
                entry = project_dir / name
                if entry.exists():
                    cmd = ["uvicorn", f"{entry.stem}:app", "--host", "0.0.0.0", "--port", str(port)]
                    return subprocess.Popen(cmd, cwd=str(project_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif stack == "node":
            pkg = project_dir / "package.json"
            if pkg.exists():
                env = {"PORT": str(port), "HOST": "0.0.0.0"}
                return subprocess.Popen(
                    ["npm", "start"], cwd=str(project_dir), env={**__import__("os").environ, **env},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
        return None

    def _assign_port(self) -> int | None:
        for offset in range(_MAX_PREVIEWS):
            port = _BASE_PORT + offset
            if port not in self._port_registry and not self._port_open(port):
                return port
        return None

    @staticmethod
    def _port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", port)) == 0
```

---

## Reverse Proxy

The FastAPI server needs a reverse proxy endpoint so the frontend iframe can reach the preview process without exposing arbitrary ports to the user's browser:

**File:** `backend/app/api/preview.py`

```python
import httpx
from fastapi import APIRouter, Request, HTTPException, Response

router = APIRouter(prefix="/preview", tags=["preview"])

@router.api_route("/{project_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_preview(project_id: str, path: str, request: Request):
    preview = container.preview_manager.health(project_id)
    if preview["status"] not in ("running", "starting"):
        raise HTTPException(status_code=503, detail="Preview not running")
    port = preview["port"]
    url = f"http://127.0.0.1:{port}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=dict(request.headers),
            content=await request.body(),
            timeout=10.0,
        )
    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
```

---

## Integration: Pipeline → PreviewManager

**File:** `backend/app/workflow/pipeline_supervisor.py`

After each sprint that passes R2 verification:
```python
# After _run_sandbox() returns success:
if sandbox_result.build.success:
    port = self._preview_manager.start(project_id, project_dir, sandbox_result.stack)
    if port:
        self._memory_manager.store(f"preview:port:{project_id}", str(port))
        logger.info("[Pipeline] preview started for %s on port %d", project_id, port)
```

---

## API Endpoints

### GET /projects/{id}/preview/status
```json
{"status": "running", "port": 9001, "url": "/preview/{id}/"}
```

### POST /projects/{id}/preview/restart
Stops and restarts the preview process (useful after a sprint update).

### DELETE /projects/{id}/preview
Stops the preview process for the project.

---

## UI Changes

**WorkspacePage:** Add "Live Preview" tab alongside "Files" and "Git History".

The preview tab shows:
- Status indicator: 🟢 Running / 🟡 Starting / 🔴 Not running / 💥 Crashed
- Iframe pointing to `/preview/{project_id}/`
- "Restart Preview" button
- Logs pane (last 50 lines from preview process stderr) for debugging

**Sprint card:** Add "View Preview" button that switches to preview tab and reloads the iframe.

---

## Security Constraints

- Preview processes must not be able to access other projects' workspace directories
- Idle timeout: stop preview processes after 30 minutes of no activity (last iframe load)
- On server startup: kill any orphaned preview PIDs stored in the preview registry
- Preview proxy route must validate that the project belongs to the authenticated user (after R8)

---

## Exit Criteria

- [ ] After a backend sprint with `sandbox_result.build.success=True`, preview process starts automatically
- [ ] `GET /preview/{project_id}/` returns HTTP 200 via the proxy (app is running)
- [ ] UI shows live iframe in WorkspacePage preview tab
- [ ] After a new sprint, preview restarts automatically showing updated app
- [ ] `GET /projects/{id}/preview/status` returns correct status (running/starting/crashed)
- [ ] Idle previews are stopped after 30 minutes
- [ ] All R1 + R2 + R3 + R4 exit criteria still passing

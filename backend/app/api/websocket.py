from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import os

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

# Cache API keys once at module import time — same pattern as APIKeyMiddleware.
# Reading the env var on every WebSocket connection caused HTTP and WebSocket
# endpoints to diverge if os.environ was mutated between requests (test reload,
# dynamic config).  A module-level constant keeps them consistent.
def _load_api_keys() -> set[str]:
    raw = os.getenv("VALID_API_KEYS", "")
    if not raw:
        return set()  # empty = auth disabled (dev mode)
    return {k.strip() for k in raw.split(",") if k.strip()}

_VALID_API_KEYS: set[str] = _load_api_keys()


def _is_valid_token(token: str) -> bool:
    """Return True if token is valid, or if auth is disabled (no keys configured)."""
    if not _VALID_API_KEYS:
        return True  # dev mode — no keys configured
    import hmac
    return any(hmac.compare_digest(token, k) for k in _VALID_API_KEYS)

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per project.

    Multiple browser tabs can connect to the same project.
    When a pipeline event fires, all connected tabs get it.
    """

    def __init__(self) -> None:
        # project_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        await websocket.accept()
        if project_id not in self._connections:
            self._connections[project_id] = []
        self._connections[project_id].append(websocket)
        logger.info(
            "WebSocket connected: project=%s total=%d",
            project_id,
            len(self._connections[project_id]),
        )

    def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        if project_id in self._connections:
            self._connections[project_id] = [
                ws for ws in self._connections[project_id] if ws is not websocket
            ]
            if not self._connections[project_id]:
                del self._connections[project_id]
        logger.info("WebSocket disconnected: project=%s", project_id)

    async def broadcast(self, project_id: str, message: dict) -> None:
        """Send message to all connections for a project."""
        connections = self._connections.get(project_id, [])
        if not connections:
            return

        payload = json.dumps(message, default=str)
        dead = []
        for ws in connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
            except Exception as e:
                logger.warning("WebSocket send failed: %s", e)
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            self.disconnect(ws, project_id)

    def has_connections(self, project_id: str) -> bool:
        return bool(self._connections.get(project_id))

    def broadcast_sync(self, project_id: str, message: dict) -> None:
        """
        A synchronous wrapper to broadcast a message to a WebSocket.
        This gets the running event loop and schedules the async broadcast coroutine
        to be executed without blocking the synchronous caller.
        """
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.broadcast(project_id, message), loop)
        except RuntimeError:
            logger.error("No running asyncio event loop found for broadcast_sync.")
        except Exception as e:
            logger.error("Error in broadcast_sync: %s", e)


# Singleton — shared across all requests
ws_manager = ConnectionManager()


@router.websocket("/ws/{project_id}")
@router.websocket("/api/ws/{project_id}")
@router.websocket("/api/v1/ws/{project_id}")
@router.websocket("/v1/ws/{project_id}")
async def project_websocket(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(default=""),
) -> None:
    """WebSocket endpoint for a project.

    BUG-6 fix: validates the token query param against VALID_API_KEYS before
    accepting the connection. In dev mode (no keys configured) all connections
    are accepted. In production, clients must pass ?token=<api_key>.

    Client connects once and receives all pipeline events in real time without polling.
    """
    if not _is_valid_token(token):
        logger.warning("WebSocket rejected: invalid token for project=%s", project_id)
        await websocket.close(code=4001)
        return
    await ws_manager.connect(websocket, project_id)
    try:
        # Send current state immediately on connect
        await websocket.send_text(
            json.dumps({
                "type": "connected",
                "project_id": project_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )

        # Keep connection alive, handle incoming messages
        while True:
            try:
                # Wait for client message or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)

                # Handle ping/pong
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

            except asyncio.TimeoutError:
                # Send keepalive ping
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps({"type": "ping"}))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", project_id)
    except Exception as e:
        logger.error("WebSocket error for project %s: %s", project_id, e)
    finally:
        ws_manager.disconnect(websocket, project_id)

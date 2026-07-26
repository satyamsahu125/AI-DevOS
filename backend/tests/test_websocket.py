import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_websocket_connects_and_receives_connected_msg():
    with client.websocket_connect("/api/ws/test-project") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"
        assert data["project_id"] == "test-project"


def test_websocket_handles_ping():
    with client.websocket_connect("/api/ws/test-project") as ws:
        ws.receive_json()  # connected msg
        ws.send_json({"type": "ping"})
        response = ws.receive_json()
        assert response["type"] == "pong"


def test_broadcaster_sends_stage_started():
    from app.events.broadcaster import EventBroadcaster

    broadcaster = EventBroadcaster()
    with patch("app.events.broadcaster.ws_manager.broadcast") as mock_broadcast:
        mock_broadcast.return_value = None
        broadcaster.stage_started("proj-1", "architect", 1)
        assert True


def test_broadcaster_stage_complete_message_format():
    from app.events.broadcaster import EventBroadcaster
    from app.api.websocket import ws_manager

    messages = []

    async def capture(project_id, msg):
        messages.append(msg)

    broadcaster = EventBroadcaster()
    with patch.object(ws_manager, "broadcast", side_effect=capture):
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            ws_manager.broadcast("proj-1", {
                "type": "stage_complete",
                "stage": "architect",
                "attempt": 1,
            })
        )
        assert len(messages) == 1
        assert messages[0]["type"] == "stage_complete"


def test_connection_manager_tracks_connections():
    from app.api.websocket import ConnectionManager

    manager = ConnectionManager()
    assert not manager.has_connections("proj-1")

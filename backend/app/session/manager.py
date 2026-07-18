from __future__ import annotations


class SessionManager:
    """Manages simple session lifecycle state."""

    def create_session(self, stage: str) -> dict[str, object]:
        return {"stage": stage, "status": "active"}

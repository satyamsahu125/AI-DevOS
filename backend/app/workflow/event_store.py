"""EventStore - Append-only event log for workflow execution.

Dual-write pattern: events are appended alongside existing workflow.json
writes without replacing them. The event log becomes the source of
truth for replay and observability.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..shared.models.workflow_event import WorkflowEvent
from ..storage.storage_adapter import StorageAdapter, StorageQuery


class EventType(str):
    """Event types for workflow execution."""
    WORKFLOW_STARTED = "workflow.started"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"


class EventStore:
    """Append-only event store for workflow execution.

    Dual-write pattern: events are appended alongside existing workflow.json
    writes without replacing them. The event log becomes the source of
    truth for replay and observability.
    """

    def __init__(self, adapter: StorageAdapter):
        self._adapter = adapter
        self._table = "workflow_events"

    def append(
        self,
        workflow_id: str,
        event_type: str,
        actor: str,
        stage: str | None = None,
        artifact_id: str | None = None,
        payload: dict | None = None,
        trace_id: str | None = None,
    ) -> WorkflowEvent:
        """Append an event to the workflow event log.

        Args:
            workflow_id: Project/workflow identifier
            event_type: Type of event (see EventType)
            actor: Who/what caused the event (agent name, "system", "engine", etc.)
            stage: Stage name if applicable
            artifact_id: Related artifact ID if applicable
            payload: Additional JSON-serializable data
            trace_id: Correlation ID for distributed tracing

        Returns:
            The created WorkflowEvent object
        """
        event = WorkflowEvent(
            event_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            event_type=event_type,
            actor=actor,
            stage=stage,
            artifact_id=artifact_id,
            payload=payload or {},
            trace_id=trace_id,
        )
        
        # Store as JSON in the generic data column (StorageAdapter schema)
        self._adapter.insert(self._table, {
            "id": event.event_id,
            "workflow_id": event.workflow_id,
            "trace_id": event.trace_id,
            "stage": event.stage,
            "event_type": event.event_type,
            "actor": event.actor,
            "artifact_id": event.artifact_id,
            "payload": json.dumps(event.payload),
            "created_at": event.created_at.isoformat() if isinstance(event.created_at, datetime) else event.created_at,
        })
        return event

    def get_history(self, workflow_id: str) -> list[WorkflowEvent]:
        """Get all events for a workflow in chronological order."""
        result = self._adapter.select(StorageQuery(
            table=self._table,
            filters={"workflow_id": workflow_id},
            order_by=["created_at"],
        ))
        
        events = []
        for row in result.rows:
            # Handle JSON payload
            payload = row.get("payload", "{}")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            
            event = WorkflowEvent(
                event_id=row.get("id", ""),
                workflow_id=row.get("workflow_id", ""),
                trace_id=row.get("trace_id"),
                stage=row.get("stage"),
                event_type=row.get("event_type", ""),
                actor=row.get("actor", ""),
                artifact_id=row.get("artifact_id"),
                payload=payload,
                created_at=row.get("created_at", ""),
            )
            events.append(event)
        return events

    def replay_state(self, workflow_id: str) -> dict:
        """
        Derive current workflow state from event log.

        Returns a dict compatible with the existing workflow state shape.
        Later this replaces reading workflow.json entirely.
        """
        events = self.get_history(workflow_id)
        if not events:
            return {}

        state = {
            "workflow_id": workflow_id,
            "status": "unknown",
            "current_stage": None,
            "completed_stages": [],
            "failed_stages": [],
            "artifact_ids": [],
            "started_at": None,
            "completed_at": None,
        }

        for e in events:
            if e.event_type == "workflow.started":
                state["status"] = "running"
                state["started_at"] = e.created_at
            elif e.event_type == "stage.started":
                state["current_stage"] = e.stage
                state["status"] = "running"
            elif e.event_type == "stage.completed":
                state["completed_stages"].append(e.stage)
                if e.artifact_id:
                    state["artifact_ids"].append(e.artifact_id)
            elif e.event_type == "stage.failed":
                state["failed_stages"].append(e.stage)
                state["status"] = "failed"
            elif e.event_type == "approval.requested":
                state["status"] = "waiting_for_review"
            elif e.event_type == "approval.granted":
                state["status"] = "running"
            elif e.event_type == "approval.denied":
                state["status"] = "failed"
            elif e.event_type == "workflow.completed":
                state["status"] = "completed"
                state["completed_at"] = e.created_at
            elif e.event_type == "workflow.failed":
                state["status"] = "failed"
                state["completed_at"] = e.created_at

        return state
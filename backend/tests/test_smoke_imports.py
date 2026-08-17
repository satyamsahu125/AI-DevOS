"""Smoke tests — verify the application can import without errors.

These tests cost nothing to run and catch missing-file ImportErrors
before they reach production.
"""

import pytest


def test_fastapi_app_imports():
    from app.main import app
    assert app is not None


def test_workflow_engine_imports():
    from app.workflow.engine import WorkflowEngine
    assert WorkflowEngine is not None


def test_event_store_imports():
    from app.workflow.event_store import EventStore, EventType
    assert EventStore is not None
    # EventType is a str subclass with class attributes, not an Enum
    assert hasattr(EventType, 'WORKFLOW_STARTED')
    assert hasattr(EventType, 'STAGE_STARTED')
    assert hasattr(EventType, 'STAGE_COMPLETED')
    assert hasattr(EventType, 'STAGE_FAILED')
    assert hasattr(EventType, 'APPROVAL_REQUESTED')
    assert hasattr(EventType, 'APPROVAL_GRANTED')
    assert hasattr(EventType, 'APPROVAL_DENIED')
    assert hasattr(EventType, 'WORKFLOW_COMPLETED')
    assert hasattr(EventType, 'WORKFLOW_FAILED')
    assert hasattr(EventType, 'WORKFLOW_CANCELLED')


def test_artifact_contracts_import():
    from app.artifacts.contracts import (
        RequirementsArtifact, ArchitectureArtifact,
        CodingArtifact, ReviewArtifact, GenericArtifact,
    )
    assert RequirementsArtifact is not None


def test_gate_config_loads():
    from app.workflow.gate_config import GateConfigLoader
    loader = GateConfigLoader()
    gate = loader.get("ProductOwner")
    assert gate.review_type == "human"
    gate_default = loader.get("nonexistent_stage_xyz")
    assert gate_default.review_type is not None   # defaults apply


def test_agent_factory_imports():
    from app.agents.factory import AgentFactory
    assert AgentFactory is not None
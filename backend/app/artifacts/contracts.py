"""Artifact output contracts for critical pipeline stages.

These Pydantic models define the expected structure of agent outputs.
Every artifact write goes through a contract so malformed outputs
fail loudly instead of silently corrupting the pipeline.

Contracts are based on what agents actually return today (inspected
from TechLeadAgent, BackendDeveloperAgent, FrontendDeveloperAgent, etc.).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core stage contracts (minimum viable)
# ---------------------------------------------------------------------------

class RequirementsArtifact(BaseModel):
    """Output from ProductOwner / requirements clarification."""
    user_stories: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    nfrs: dict[str, Any] = Field(default_factory=dict)


class ArchitectureArtifact(BaseModel):
    """Output from Architect."""
    components: list[str] = Field(default_factory=list)
    tech_stack: dict[str, str] = Field(default_factory=dict)
    data_flows: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    api_endpoints: list[dict[str, str]] = Field(default_factory=list)
    modules: list[dict[str, Any]] = Field(default_factory=list)


class CodingArtifact(BaseModel):
    """Output from BackendDeveloper / FrontendDeveloper."""
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    summary: str = ""


class ReviewArtifact(BaseModel):
    """Output from TechLeadAgent / Reviewer."""
    approved: bool
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    iteration: int = 1


class DesignArtifact(BaseModel):
    """Output from Designer."""
    pages: list[str] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    design_system: dict[str, Any] = Field(default_factory=dict)


class QAArtifact(BaseModel):
    """Output from QAAgent."""
    test_files: list[str] = Field(default_factory=list)
    test_count: int = 0
    passed: int = 0
    failed: int = 0
    coverage: dict[str, Any] = Field(default_factory=dict)


class DevOpsArtifact(BaseModel):
    """Output from DevOpsAgent."""
    dockerfile: str = ""
    docker_compose: str = ""
    ci_config: str = ""
    env_template: str = ""


class SecurityArtifact(BaseModel):
    """Output from SecurityAgent."""
    vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    compliance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage → Contract mapping
# ---------------------------------------------------------------------------

STAGE_CONTRACTS: dict[str, type] = {
    "requirements": RequirementsArtifact,
    "product_owner": RequirementsArtifact,
    "architecture": ArchitectureArtifact,
    "architect": ArchitectureArtifact,
    "design": DesignArtifact,
    "designer": DesignArtifact,
    "coding": CodingArtifact,
    "backend": CodingArtifact,
    "backenddeveloper": CodingArtifact,
    "frontend": CodingArtifact,
    "frontenddeveloper": CodingArtifact,
    "review": ReviewArtifact,
    "tech_lead": ReviewArtifact,
    "techlead": ReviewArtifact,
    "qa": QAArtifact,
    "devops": DevOpsArtifact,
    "security": SecurityArtifact,
}


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

class GenericArtifact(BaseModel):
    """Fallback for stages without a specific contract."""
    output: dict[str, Any] = Field(default_factory=dict)
    stage: str = ""


def get_contract(stage: str) -> type:
    """Get the contract class for a stage name (case-insensitive)."""
    return STAGE_CONTRACTS.get(stage.lower(), GenericArtifact)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ArtifactContractViolation(RuntimeError):
    """Raised when agent output fails contract validation."""
    pass
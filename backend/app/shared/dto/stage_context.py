from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..enums.stage import Stage


@dataclass
class StageContext:
    """Typed context assembled by MemoryOrchestrator for one stage execution.

    Replaces the untyped string content that WorkflowEngine previously built
    via six ad-hoc _with_*() enrichment methods. Every stage receives exactly
    this object; prompt builders access named fields instead of parsing strings.

    All fields are optional/default-empty — MemoryOrchestrator fills what it
    can and leaves the rest empty. Prompt builders check is_populated flags
    rather than assuming data is present.
    """

    project_id: str = ""
    stage: Stage | None = None

    # Core request data
    original_request: str = ""

    # Episodic memory — per-stage approved outputs (keyed by stage name string)
    predecessor_outputs: dict[str, Any] = field(default_factory=dict)

    # Typed structured artifacts for the most commonly needed stages
    clarification: dict | None = None        # ClarificationArtifact dict
    strategic_brief: dict | None = None      # StrategicBrief dict
    domain_research: dict | None = None      # DomainResearch dict
    design_artifact: dict | None = None      # DesignArtifact dict
    architecture_artifact: dict | None = None  # ArchitectureArtifact dict

    # Semantic memory — cross-project learning
    lessons: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)

    # Procedural memory — live project intelligence
    intelligence: dict | None = None         # FileIndexer + DependencyGraph output

    # Budget and metadata
    token_budget: int = 16384
    assembled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_prompt_dict(self) -> dict[str, Any]:
        """Serialise to the JSON dict format ProductOwnerPromptBuilder (Path A) expects.

        This is the canonical way to convert a StageContext into LLM-readable content.
        All prompt builders should call this instead of receiving raw strings.
        """
        return {
            "original_request": self.original_request,
            "clarification": self.clarification or {},
            "strategic_brief": self.strategic_brief or {},
            "domain_research": self.domain_research or {},
            "design_artifact": self.design_artifact or {},
            "architecture_artifact": self.architecture_artifact or {},
            "lessons": self.lessons,
            "patterns": self.patterns,
            "intelligence": self.intelligence or {},
        }

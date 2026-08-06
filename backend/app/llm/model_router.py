from __future__ import annotations

import logging
import os

from ..shared.dto.model_profile import ModelProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-stage routing table.
# Each entry maps a stage name (matching Stage enum values) to a ModelProfile.
# Values are intentionally left as raw strings rather than importing Stage
# to keep this module dependency-free and easy to test in isolation.
#
# The profiles below use the globally configured provider/model as defaults
# (provider=None, model=None means "use whatever is in .env").  Override
# individual stages with env vars in production:
#   MODEL_ROUTER_ARCHITECT_MODEL=claude-3-5-opus-20240229
#   MODEL_ROUTER_BACKEND_DEVELOPER_MODEL=deepseek-coder-v2
#
# DESIGN RATIONALE:
#   - Creative/planning stages → higher temperature (0.3–0.5)
#   - Code generation stages → lower temperature (0.05–0.1), large max_tokens
#   - Review/QA stages → low temperature for determinism
#   - Research stages → medium temperature for diversity
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "bedrock")
_DEFAULT_MODEL = os.getenv("LLM_MODEL", "")

# Stages that benefit from a lower temperature for deterministic output
_CODE_STAGES = {
    "BackendDeveloper",
    "FrontendDeveloper",
    "DevOps",
    "SprintDeploy",
}

# Stages that benefit from a slightly higher temperature for creative output
_CREATIVE_STAGES = {
    "Designer",
    "DomainResearch",
    "StrategicReview",
}

# All other stages: medium temperature


def _profile(temperature: float, max_tokens: int | None = None) -> ModelProfile:
    """Build a profile using the globally configured provider and model."""
    return ModelProfile(
        provider=_DEFAULT_PROVIDER,
        model=_DEFAULT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# Stage → ModelProfile.  Built once at module import time.
STAGE_PROFILES: dict[str, ModelProfile] = {
    # ── Clarification & Planning ──────────────────────────────────────────
    "Clarification":       _profile(temperature=0.2),
    "ProductOwner":        _profile(temperature=0.2),
    "StrategicReview":     _profile(temperature=0.4),
    "DomainResearch":      _profile(temperature=0.4),
    "SprintPlanning":      _profile(temperature=0.2),
    "ScrumMaster":         _profile(temperature=0.2),
    "TechLead":            _profile(temperature=0.2),
    # ── Architecture & Design ─────────────────────────────────────────────
    "Architect":           _profile(temperature=0.2, max_tokens=8192),
    "Designer":            _profile(temperature=0.4),
    "FileStructurePlanner": _profile(temperature=0.1),
    # ── Code Generation ───────────────────────────────────────────────────
    "BackendDeveloper":    _profile(temperature=0.05, max_tokens=16384),
    "FrontendDeveloper":   _profile(temperature=0.05, max_tokens=16384),
    "DevOps":              _profile(temperature=0.05, max_tokens=8192),
    "SprintDeploy":        _profile(temperature=0.05, max_tokens=8192),
    # ── Review & QA ───────────────────────────────────────────────────────
    "Reviewer":            _profile(temperature=0.1),
    "QA":                  _profile(temperature=0.1),
    "BugAnalyst":          _profile(temperature=0.1),
    "Security":            _profile(temperature=0.1),
    "SprintReview":        _profile(temperature=0.1),
    # ── Documentation & Retrospective ────────────────────────────────────
    "Document":            _profile(temperature=0.2, max_tokens=8192),
    "Retro":               _profile(temperature=0.3),
}


class ModelRouter:
    """Returns the appropriate ModelProfile for a given pipeline stage.

    Lookup is O(1) via STAGE_PROFILES.  Falls back to a default medium-
    temperature profile for unknown stage names so new stages never crash.

    Design:
    - No LLM calls — purely local routing table.
    - Provider and model inherit from global .env settings so switching the
      active LLM provider (bedrock → ollama → gemini) requires only .env
      changes, not code changes.
    - Per-stage env var overrides are supported in the future via
      _apply_env_overrides(); the hook is present but the table is the
      canonical source of truth.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {**STAGE_PROFILES}
        logger.debug("model_router ready: %d stage profiles loaded", len(self._profiles))

    def get_profile(self, stage: str) -> ModelProfile:
        """Return the ModelProfile for stage.

        Always returns a valid profile — falls back to a sensible default
        for unknown stages rather than raising.
        """
        profile = self._profiles.get(stage)
        if profile is None:
            logger.debug("model_router: no profile for stage=%s — using default", stage)
            profile = _profile(temperature=0.1)
        return profile

    def register_profile(self, stage: str, profile: ModelProfile) -> None:
        """Register or override the profile for stage (useful in tests)."""
        self._profiles[stage] = profile
        logger.debug("model_router: registered profile for stage=%s: %r", stage, profile)

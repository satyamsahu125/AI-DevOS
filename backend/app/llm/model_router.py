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
    - Per-stage env var overrides are checked at call time (P7-6):
        STAGE_{STAGE_UPPER}_PROVIDER  — overrides provider for that stage only
        STAGE_{STAGE_UPPER}_MODEL     — overrides model for that stage only
      Example: STAGE_PRODUCTOWNER_MODEL=claude-opus-5
               STAGE_BACKENDDEVELOPER_PROVIDER=bedrock
      temperature and max_tokens are always taken from STAGE_PROFILES.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {**STAGE_PROFILES}
        logger.debug("model_router ready: %d stage profiles loaded", len(self._profiles))

    def get_profile(self, stage: str) -> ModelProfile:
        """Return the ModelProfile for stage.

        Priority (highest → lowest):
          1. Per-stage env vars: STAGE_{STAGE_UPPER}_PROVIDER / STAGE_{STAGE_UPPER}_MODEL
          2. STAGE_PROFILES table entry for this stage
          3. Global fallback (_DEFAULT_PROVIDER / _DEFAULT_MODEL, temperature=0.1)

        temperature and max_tokens are always sourced from STAGE_PROFILES (or
        the default); env vars can only override provider and model.

        Always returns a valid profile — never raises.
        """
        # Resolve the base profile from the routing table (or the global default).
        base = self._profiles.get(stage)
        if base is None:
            logger.debug("model_router: no profile for stage=%s — using default", stage)
            base = _profile(temperature=0.1)

        # P7-6: check per-stage env-var overrides (read at call time, not import time).
        stage_key = stage.upper()
        env_provider = os.getenv(f"STAGE_{stage_key}_PROVIDER")
        env_model = os.getenv(f"STAGE_{stage_key}_MODEL")

        if env_provider is not None or env_model is not None:
            overridden = ModelProfile(
                provider=env_provider if env_provider is not None else base.provider,
                model=env_model if env_model is not None else base.model,
                temperature=base.temperature,
                max_tokens=base.max_tokens,
            )
            logger.debug(
                "model_router: env override for stage=%s: provider=%r model=%r → %r",
                stage, env_provider, env_model, overridden,
            )
            return overridden

        return base

    def register_profile(self, stage: str, profile: ModelProfile) -> None:
        """Register or override the profile for stage (useful in tests)."""
        self._profiles[stage] = profile
        logger.debug("model_router: registered profile for stage=%s: %r", stage, profile)


# ---------------------------------------------------------------------------
# P9-2a: Profile validation
#
# validate_profile() returns a list of human-readable error strings (empty = valid).
# validate_all_stage_profiles() runs validate_profile() across every entry in
# STAGE_PROFILES and returns a mapping of stage → errors (omitting valid stages).
#
# Constraints are derived from documented LLM API invariants — not invented:
#   - provider: must be a non-empty string (model_router.py explicitly sets
#     provider from LLM_PROVIDER env var; empty provider has no valid meaning).
#   - model: any string including empty ("" means inherit from env, documented).
#   - temperature: if set, must be float in [0.0, 1.0] (all LLM providers
#     enforce this range; temperatures outside it are API errors).
#   - max_tokens: if set, must be a positive int (zero or negative makes no
#     sense for an output token budget).
# ---------------------------------------------------------------------------


def validate_profile(profile: ModelProfile) -> list[str]:
    """Validate a ModelProfile against documented constraints.

    Returns a list of error strings.  An empty list means the profile is valid.

    Args:
        profile: The ModelProfile to validate.

    Returns:
        List of human-readable error strings (empty → valid).
    """
    errors: list[str] = []

    # provider must be a non-empty string.
    if not isinstance(profile.provider, str) or not profile.provider.strip():
        errors.append(
            f"provider must be a non-empty string, got {profile.provider!r}"
        )

    # model can be any string (empty means inherit from env).
    if not isinstance(profile.model, str):
        errors.append(f"model must be a string, got {type(profile.model).__name__!r}")

    # temperature: if set, must be float in [0.0, 1.0].
    if profile.temperature is not None:
        if not isinstance(profile.temperature, (int, float)):
            errors.append(
                f"temperature must be a float, got {type(profile.temperature).__name__!r}"
            )
        elif not (0.0 <= float(profile.temperature) <= 1.0):
            errors.append(
                f"temperature={profile.temperature} is out of valid range [0.0, 1.0]"
            )

    # max_tokens: if set, must be a positive int.
    if profile.max_tokens is not None:
        if not isinstance(profile.max_tokens, int):
            errors.append(
                f"max_tokens must be an int, got {type(profile.max_tokens).__name__!r}"
            )
        elif profile.max_tokens <= 0:
            errors.append(
                f"max_tokens={profile.max_tokens} must be a positive integer (≥ 1)"
            )

    return errors


def validate_all_stage_profiles() -> dict[str, list[str]]:
    """Run validate_profile() across every entry in STAGE_PROFILES.

    Returns a dict mapping stage name → list of error strings for that stage.
    Stages with no errors are omitted from the result (empty dict = all valid).

    Useful for startup assertions and for the analytics/profiles API endpoint.
    """
    invalid: dict[str, list[str]] = {}
    for stage_name, profile in STAGE_PROFILES.items():
        errs = validate_profile(profile)
        if errs:
            invalid[stage_name] = errs
    return invalid

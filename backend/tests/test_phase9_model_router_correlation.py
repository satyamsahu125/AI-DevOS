"""test_phase9_model_router_correlation.py — P9-2a focused tests.

Covers:
  1.  Valid ModelProfile accepted by validate_profile().
  2.  Invalid temperature rejected (> 1.0).
  3.  Invalid temperature rejected (< 0.0).
  4.  Invalid max_tokens rejected (zero).
  5.  Invalid provider (empty string) rejected.
  6.  Every entry in STAGE_PROFILES passes validation.
  7.  Trajectory with approved=True is counted in approvals.
  8.  Trajectory with approved=False is counted in rejections.
  9.  Approval rate = approved / total.
  10. Grouping by stage — two stages produce two result groups.
  11. Grouping by temperature — results annotated with STAGE_PROFILES temperature.
  12. Grouping by model/provider — different agent_models produce separate groups.
  13. Project isolation — project A trajectories do not appear in project B results.
  14. Empty trajectory dataset returns valid empty result (no exception).
  15. Deterministic ordering — identical data always yields same order.
  16. API response schema — model-correlation endpoint returns required keys.
  17. API profiles endpoint — includes temperature in model_profile per stage.
  18. No sensitive prompt/context leakage — task_description, reviewer_feedback
      absent from model-correlation response.

Running:
    cd backend
    python -m pytest tests/test_phase9_model_router_correlation.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_learning_loop(tmp_path: Path):
    """Build a real LearningLoop backed by a temporary SQLite file."""
    from app.memory.learning_loop import LearningLoop
    from unittest.mock import MagicMock

    km = MagicMock()
    km.search.return_value = []
    db = tmp_path / "test_learning.sqlite"
    return LearningLoop(knowledge_memory=km, db_path=db)


def _record(ll, stage: str, agent_model: str, approved: bool, project_id: str = "proj-1") -> None:
    """Record a minimal trajectory into LearningLoop."""
    from app.memory.learning_loop import Trajectory
    from datetime import datetime, timezone

    t = Trajectory(
        stage=stage,
        task_description="build something",   # sensitive-ish but not leaked in correlation
        artifact_summary="here is the artifact",
        retry_count=0,
        approved=approved,
        reviewer_feedback="looks good" if approved else "needs work",
        agent_model=agent_model,
        tokens_used=1000,
        latency_ms=500.0,
        recorded_at=datetime.now(timezone.utc),
        project_id=project_id,
    )
    ll.record_trajectory(t, project_id=project_id)


# ---------------------------------------------------------------------------
# 1–5: Profile validation — validate_profile()
# ---------------------------------------------------------------------------


class TestValidateProfile:
    """validate_profile() accepts valid profiles and rejects invalid ones."""

    def test_valid_profile_accepted(self):
        """A well-formed ModelProfile must return an empty error list."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="claude-3", temperature=0.2, max_tokens=8192)
        errors = validate_profile(p)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_temperature_above_one_rejected(self):
        """temperature > 1.0 must produce an error."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=1.5)
        errors = validate_profile(p)
        assert len(errors) == 1
        assert "temperature" in errors[0].lower()

    def test_temperature_below_zero_rejected(self):
        """temperature < 0.0 must produce an error."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=-0.1)
        errors = validate_profile(p)
        assert len(errors) == 1
        assert "temperature" in errors[0].lower()

    def test_max_tokens_zero_rejected(self):
        """max_tokens=0 must produce an error (must be positive)."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=0.2, max_tokens=0)
        errors = validate_profile(p)
        assert len(errors) == 1
        assert "max_tokens" in errors[0].lower()

    def test_empty_provider_rejected(self):
        """provider='' must produce an error."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="", model="", temperature=0.2)
        errors = validate_profile(p)
        assert len(errors) == 1
        assert "provider" in errors[0].lower()

    def test_model_empty_string_accepted(self):
        """model='' is valid (means inherit from env, documented behaviour)."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=0.1)
        errors = validate_profile(p)
        assert errors == []

    def test_temperature_boundary_zero_accepted(self):
        """temperature=0.0 is a valid boundary value."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=0.0)
        assert validate_profile(p) == []

    def test_temperature_boundary_one_accepted(self):
        """temperature=1.0 is a valid boundary value."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=1.0)
        assert validate_profile(p) == []

    def test_max_tokens_negative_rejected(self):
        """max_tokens < 0 must produce an error."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", max_tokens=-1)
        errors = validate_profile(p)
        assert any("max_tokens" in e.lower() for e in errors)

    def test_max_tokens_none_accepted(self):
        """max_tokens=None is valid (inherits from LLM provider default)."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=0.2, max_tokens=None)
        assert validate_profile(p) == []

    def test_temperature_none_accepted(self):
        """temperature=None is valid (inherits from LLM provider default)."""
        from app.shared.dto.model_profile import ModelProfile
        from app.llm.model_router import validate_profile

        p = ModelProfile(provider="bedrock", model="", temperature=None)
        assert validate_profile(p) == []


# ---------------------------------------------------------------------------
# 6: Every STAGE_PROFILE passes validation
# ---------------------------------------------------------------------------


class TestAllStageProfilesValid:
    """validate_all_stage_profiles() must report zero errors for every built-in stage."""

    def test_all_stage_profiles_pass_validation(self):
        """validate_all_stage_profiles() must return an empty dict (all valid)."""
        from app.llm.model_router import validate_all_stage_profiles

        errors = validate_all_stage_profiles()
        assert errors == {}, (
            f"The following STAGE_PROFILES have validation errors:\n"
            + "\n".join(f"  {stage}: {errs}" for stage, errs in errors.items())
        )

    def test_validate_all_returns_dict(self):
        """validate_all_stage_profiles() must always return a dict."""
        from app.llm.model_router import validate_all_stage_profiles

        result = validate_all_stage_profiles()
        assert isinstance(result, dict)

    def test_stage_profiles_non_empty(self):
        """STAGE_PROFILES must contain at least 10 stages."""
        from app.llm.model_router import STAGE_PROFILES

        assert len(STAGE_PROFILES) >= 10, f"Expected ≥10 profiles, got {len(STAGE_PROFILES)}"


# ---------------------------------------------------------------------------
# 7–15: Trajectory correlation — LearningLoop.get_trajectory_correlation()
# ---------------------------------------------------------------------------


class TestTrajectoryCorrelation:
    """get_trajectory_correlation() correctly aggregates approval statistics."""

    def test_approved_trajectory_counted_in_approvals(self, tmp_path):
        """A trajectory with approved=True must increment the approvals counter."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True)

        groups = ll.get_trajectory_correlation(stage="Architect")
        assert len(groups) == 1
        assert groups[0]["approved"] == 1
        assert groups[0]["rejected"] == 0
        assert groups[0]["total"] == 1

    def test_rejected_trajectory_counted_in_rejections(self, tmp_path):
        """A trajectory with approved=False must increment the rejections counter."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "QA", "claude-3", approved=False)

        groups = ll.get_trajectory_correlation(stage="QA")
        assert len(groups) == 1
        assert groups[0]["rejected"] == 1
        assert groups[0]["approved"] == 0
        assert groups[0]["total"] == 1

    def test_approval_rate_calculation(self, tmp_path):
        """approval_rate must equal approved / total."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "BackendDeveloper", "claude-3", approved=True)
        _record(ll, "BackendDeveloper", "claude-3", approved=True)
        _record(ll, "BackendDeveloper", "claude-3", approved=False)

        groups = ll.get_trajectory_correlation(stage="BackendDeveloper")
        assert len(groups) == 1
        g = groups[0]
        assert g["total"] == 3
        assert g["approved"] == 2
        assert g["rejected"] == 1
        assert abs(g["approval_rate"] - round(2 / 3, 4)) < 1e-6

    def test_grouping_by_stage(self, tmp_path):
        """Trajectories from two different stages must produce two groups."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True)
        _record(ll, "BackendDeveloper", "claude-3", approved=True)

        groups = ll.get_trajectory_correlation()
        stages = {g["stage"] for g in groups}
        assert "Architect" in stages
        assert "BackendDeveloper" in stages
        assert len(stages) == 2

    def test_grouping_by_temperature(self, tmp_path):
        """Each result group must be annotated with the STAGE_PROFILES temperature for its stage."""
        from app.llm.model_router import STAGE_PROFILES

        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True)       # temp=0.2
        _record(ll, "BackendDeveloper", "claude-3", approved=True) # temp=0.05

        groups = ll.get_trajectory_correlation()
        by_stage = {g["stage"]: g for g in groups}

        assert by_stage["Architect"]["temperature"] == STAGE_PROFILES["Architect"].temperature
        assert by_stage["BackendDeveloper"]["temperature"] == STAGE_PROFILES["BackendDeveloper"].temperature
        # The temperatures must differ (Architect=0.2, BackendDeveloper=0.05)
        assert by_stage["Architect"]["temperature"] != by_stage["BackendDeveloper"]["temperature"]

    def test_grouping_by_model(self, tmp_path):
        """Different agent_model values within the same stage produce separate groups."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3-sonnet", approved=True)
        _record(ll, "Architect", "claude-3-opus",   approved=True)

        groups = ll.get_trajectory_correlation(stage="Architect")
        assert len(groups) == 2
        models = {g["model"] for g in groups}
        assert "claude-3-sonnet" in models
        assert "claude-3-opus" in models

    def test_project_isolation(self, tmp_path):
        """Filtering by project_id must exclude trajectories from other projects."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True,  project_id="proj-A")
        _record(ll, "Architect", "claude-3", approved=False, project_id="proj-B")

        groups_a = ll.get_trajectory_correlation(project_id="proj-A")
        assert len(groups_a) == 1
        assert groups_a[0]["approved"] == 1
        assert groups_a[0]["rejected"] == 0

        groups_b = ll.get_trajectory_correlation(project_id="proj-B")
        assert len(groups_b) == 1
        assert groups_b[0]["rejected"] == 1
        assert groups_b[0]["approved"] == 0

    def test_empty_dataset_returns_empty_list(self, tmp_path):
        """No trajectory data must return [] without raising an exception."""
        ll = _make_learning_loop(tmp_path)
        groups = ll.get_trajectory_correlation()
        assert groups == []

    def test_deterministic_ordering(self, tmp_path):
        """Two identical inserts must always yield the same result order."""
        ll1 = _make_learning_loop(tmp_path / "a")
        ll2 = _make_learning_loop(tmp_path / "b")

        for ll in (ll1, ll2):
            _record(ll, "QA",              "model-x", approved=True)
            _record(ll, "Architect",       "model-x", approved=False)
            _record(ll, "BackendDeveloper", "model-x", approved=True)

        g1 = ll1.get_trajectory_correlation()
        g2 = ll2.get_trajectory_correlation()
        assert [r["stage"] for r in g1] == [r["stage"] for r in g2]

    def test_result_contains_required_keys(self, tmp_path):
        """Every result group must contain all required analytics keys."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True)

        groups = ll.get_trajectory_correlation()
        required_keys = {
            "stage", "provider", "model", "temperature", "max_tokens",
            "total", "approved", "rejected", "approval_rate",
        }
        for g in groups:
            missing = required_keys - set(g.keys())
            assert not missing, f"Group missing keys: {missing}"

    def test_no_sensitive_data_in_result(self, tmp_path):
        """task_description, artifact_summary, reviewer_feedback must NOT appear in correlation result."""
        ll = _make_learning_loop(tmp_path)
        _record(ll, "Architect", "claude-3", approved=True)

        groups = ll.get_trajectory_correlation()
        sensitive_keys = {"task_description", "artifact_summary", "reviewer_feedback"}
        for g in groups:
            leaked = sensitive_keys & set(g.keys())
            assert not leaked, f"Sensitive keys leaked into correlation result: {leaked}"

    def test_provider_from_stage_profiles(self, tmp_path):
        """Result groups must include the provider from STAGE_PROFILES for that stage."""
        from app.llm.model_router import STAGE_PROFILES

        ll = _make_learning_loop(tmp_path)
        _record(ll, "BackendDeveloper", "claude-3", approved=True)

        groups = ll.get_trajectory_correlation(stage="BackendDeveloper")
        assert len(groups) == 1
        expected_provider = STAGE_PROFILES["BackendDeveloper"].provider
        assert groups[0]["provider"] == expected_provider


# ---------------------------------------------------------------------------
# 16–18: API endpoints (using FastAPI TestClient, no real LLM needed)
# ---------------------------------------------------------------------------


class TestAnalyticsAPISchema:
    """API endpoints return the expected schema without requiring real LLM or Redis.

    _get_learning_loop() in analytics.py relies on the full DI container which is
    not available in isolated TestClient tests.  We patch it to return None (the
    'no data' path) so the endpoints exercise their own logic without requiring the
    container.  get_shared_cost_tracker() is similarly patched.
    """

    def _client_and_mocks(self):
        """Build TestClient + context-manager patches for DI-coupled helpers."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from app.api.analytics import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)

        # Mock CostTracker so it doesn't hit a real sqlite file
        mock_tracker = MagicMock()
        mock_tracker.get_stage_cost.side_effect = Exception("no db in test")
        mock_tracker.get_total.return_value = MagicMock(calls=0, total_tokens=0, total_latency_ms=0)
        mock_tracker._conn = MagicMock()
        mock_tracker._conn.execute.return_value.fetchall.return_value = []
        mock_tracker._conn.execute.return_value.fetchone.return_value = (0,)

        return client, mock_tracker

    def test_model_correlation_response_schema(self):
        """GET /analytics/model-correlation must return a dict with 'groups' and 'total_trajectories'."""
        from unittest.mock import patch
        import app.api.analytics as analytics_mod

        client, mock_tracker = self._client_and_mocks()
        with patch.object(analytics_mod, "_get_learning_loop", return_value=None), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=mock_tracker):
            response = client.get("/analytics/model-correlation")

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "groups" in data, "Response missing 'groups' key"
        assert "total_trajectories" in data, "Response missing 'total_trajectories' key"
        assert isinstance(data["groups"], list)
        assert isinstance(data["total_trajectories"], int)

    def test_stage_analytics_includes_model_profile(self):
        """GET /analytics/stage/{stage} must include 'model_profile' with temperature."""
        from unittest.mock import patch
        import app.api.analytics as analytics_mod

        client, mock_tracker = self._client_and_mocks()
        with patch.object(analytics_mod, "_get_learning_loop", return_value=None), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=mock_tracker):
            response = client.get("/analytics/stage/BackendDeveloper")

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "model_profile" in data, "stage analytics missing 'model_profile' key"
        mp = data["model_profile"]
        assert "temperature" in mp, "model_profile missing 'temperature'"
        assert mp["temperature"] == pytest.approx(0.05)

    def test_profiles_endpoint_returns_all_stages(self):
        """GET /analytics/profiles must list every STAGE_PROFILES stage with valid=True."""
        from app.llm.model_router import STAGE_PROFILES
        from unittest.mock import patch
        import app.api.analytics as analytics_mod

        client, mock_tracker = self._client_and_mocks()
        # profiles endpoint only reads STAGE_PROFILES — no DI container needed
        with patch.object(analytics_mod, "_get_learning_loop", return_value=None), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=mock_tracker):
            response = client.get("/analytics/profiles")

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "profiles" in data
        assert data["all_valid"] is True
        assert data["invalid_count"] == 0
        assert set(data["profiles"].keys()) == set(STAGE_PROFILES.keys())

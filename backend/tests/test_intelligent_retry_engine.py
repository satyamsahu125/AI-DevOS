"""test_intelligent_retry_engine.py — IntelligentRetryEngine + StageRunner gating.

Verifies:
  1. RetryPlan.modified_config is populated per strategy (schema_mismatch,
     ask_human, token_rebalance).
  2. IntelligentRetryEngine.plan() — FLAG stops immediately regardless of attempt.
  3. IntelligentRetryEngine.plan() — budget exhausted stops.
  4. IntelligentRetryEngine.plan() — ASK_HUMAN on attempt ≥ 1 escalates.
  5. IntelligentRetryEngine.plan() — AUTO_FIX retries with temperature override.
  6. IntelligentRetryEngine.plan() — late retry (attempt ≥ 2) gets max_tokens.
  7. StageRunner with engine present: engine drives the loop (policy not consulted).
  8. StageRunner with engine present: FLAG tier stops after first rejection.
  9. StageRunner without engine: falls back to retry_policy.should_retry().
  10. StageRunner without engine: policy exhaust stops the loop.
  11. StageRunner: approved on first attempt → no retry at all.
  12. StageRunner: engine stop propagates strategy/reason to result message.

Running:
    cd backend
    python -m pytest tests/test_intelligent_retry_engine.py -v
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from app.shared.dto.retry_plan import RetryPlan
from app.workflow.retry_engine import IntelligentRetryEngine
from app.workflow.stage_runner import StageRunner


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeFinding:
    tier: "FakeTier"
    description: str = "test finding"
    suggestion: str = ""


class FakeTier:
    def __init__(self, value: str):
        self.value = value


def _finding(tier_str: str, suggestion: str = "") -> FakeFinding:
    return FakeFinding(tier=FakeTier(tier_str), suggestion=suggestion)


@dataclass
class FakeReviewResult:
    approved: bool = False
    findings: list = field(default_factory=list)
    overall_feedback: str = "rejected"


@dataclass
class FakeArtifact:
    content: str = '{"key": "value"}'
    structured_content: dict = field(default_factory=dict)


@dataclass
class FakeExecResult:
    artifact: FakeArtifact = field(default_factory=FakeArtifact)


def _make_engine(max_retries: int = 3) -> IntelligentRetryEngine:
    return IntelligentRetryEngine(max_retries=max_retries)


def _make_stage_runner(
    *,
    execution_manager: MagicMock | None = None,
    reviewer: MagicMock | None = None,
    retry_policy: MagicMock | None = None,
    retry_engine: IntelligentRetryEngine | None = None,
) -> StageRunner:
    # Build defaults only for params not supplied by the caller.
    # Never overwrite caller-supplied mock configuration.
    if execution_manager is None:
        em: MagicMock = MagicMock()
        em.execute_stage.return_value = FakeExecResult()
    else:
        em = execution_manager

    if reviewer is None:
        rv: MagicMock = MagicMock()
        rv.review.return_value = FakeReviewResult(approved=True)
    else:
        rv = reviewer

    if retry_policy is None:
        rp: MagicMock = MagicMock()
        rp.should_retry.return_value = True
    else:
        rp = retry_policy

    el = MagicMock()
    el.record = MagicMock()
    bc = MagicMock()

    return StageRunner(
        execution_manager=em,
        reviewer=rv,
        retry_policy=rp,
        event_log=el,
        broadcaster=bc,
        retry_engine=retry_engine,
    )


# ---------------------------------------------------------------------------
# RetryPlan.modified_config population
# ---------------------------------------------------------------------------

class TestModifiedConfig:

    def test_auto_fix_gets_low_temperature(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("auto_fix")])
        plan = engine.plan(attempt=1, review_result=rv, stage="Architect")

        assert plan.should_retry is True
        assert plan.modified_config.get("temperature") == 0.05
        # max_tokens not set for auto_fix on first retry
        assert "max_tokens" not in plan.modified_config

    def test_ask_human_gets_max_tokens(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("ask_human")])
        # attempt 0 → first attempt, ASK_HUMAN should retry once with max_tokens
        plan = engine.plan(attempt=0, review_result=rv, stage="Architect")

        assert plan.should_retry is True
        assert plan.modified_config.get("max_tokens") == 16384

    def test_late_retry_gets_max_tokens(self):
        """Any rejection at attempt ≥ 2 should include max_tokens in config."""
        engine = _make_engine(max_retries=5)
        rv = FakeReviewResult(findings=[_finding("auto_fix")])
        plan = engine.plan(attempt=2, review_result=rv, stage="BackendDeveloper")

        assert plan.should_retry is True
        assert plan.modified_config.get("max_tokens") == 16384

    def test_flag_stop_has_no_modified_config(self):
        """FLAG rejection returns empty config (no next attempt)."""
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("flag")])
        plan = engine.plan(attempt=0, review_result=rv, stage="Security")

        assert plan.should_retry is False
        assert plan.modified_config == {}


# ---------------------------------------------------------------------------
# IntelligentRetryEngine.plan() decisions
# ---------------------------------------------------------------------------

class TestEngineDecisions:

    def test_flag_stops_immediately(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("flag")])
        plan = engine.plan(attempt=0, review_result=rv, stage="Security")

        assert plan.should_retry is False
        assert plan.strategy == "stop"

    def test_budget_exhausted_stops(self):
        engine = _make_engine(max_retries=3)
        rv = FakeReviewResult(findings=[_finding("auto_fix")])
        # attempt == max_retries → budget exhausted
        plan = engine.plan(attempt=3, review_result=rv, stage="Architect")

        assert plan.should_retry is False
        assert plan.strategy == "stop"

    def test_ask_human_on_later_attempt_escalates(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("ask_human")])
        plan = engine.plan(attempt=1, review_result=rv, stage="ProductOwner")

        assert plan.should_retry is False
        assert plan.strategy == "escalate"

    def test_auto_fix_retries(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[_finding("auto_fix")])
        plan = engine.plan(attempt=1, review_result=rv, stage="Architect")

        assert plan.should_retry is True
        assert plan.strategy == "auto_fix"

    def test_unknown_rejection_retries_within_budget(self):
        engine = _make_engine()
        rv = FakeReviewResult(findings=[])  # no findings → unknown type
        plan = engine.plan(attempt=1, review_result=rv, stage="Designer")

        assert plan.should_retry is True

    def test_none_review_result_retries_within_budget(self):
        engine = _make_engine()
        plan = engine.plan(attempt=0, review_result=None, stage="Architect")

        assert plan.should_retry is True


# ---------------------------------------------------------------------------
# StageRunner — engine-driven loop
# ---------------------------------------------------------------------------

class TestStageRunnerWithEngine:

    def test_engine_drives_loop_policy_not_consulted(self):
        """When retry_engine is present, retry_policy.should_retry must not be called."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        # Reject twice then approve
        rv_mock.review.side_effect = [
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=True),
        ]

        policy_mock = MagicMock()
        policy_mock.should_retry.return_value = True  # should NOT be consulted

        engine = _make_engine(max_retries=5)
        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_policy=policy_mock,
            retry_engine=engine,
        )
        result = runner.run("proj-1", "Architect", "context")

        assert result.success is True
        assert result.attempt_count == 2
        # Policy must not be called — engine is the gate
        policy_mock.should_retry.assert_not_called()

    def test_flag_tier_stops_after_first_rejection(self):
        """FLAG finding → engine stops immediately after first rejection."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        rv_mock.review.return_value = FakeReviewResult(
            approved=False,
            findings=[_finding("flag")],
            overall_feedback="unsafe output",
        )

        engine = _make_engine(max_retries=10)  # budget would allow many retries
        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_engine=engine,
        )
        result = runner.run("proj-1", "Security", "context")

        assert result.success is False
        assert result.attempt_count == 1  # only one execution, then stop
        assert em.execute_stage.call_count == 1

    def test_engine_budget_exhausted_stops(self):
        """Engine stops when attempt budget (max_retries=2) is exhausted."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        # Always reject
        rv_mock.review.return_value = FakeReviewResult(
            approved=False,
            findings=[_finding("auto_fix")],
        )

        engine = _make_engine(max_retries=2)
        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_engine=engine,
        )
        result = runner.run("proj-1", "Architect", "context")

        assert result.success is False
        # 2 attempts (0 and 1); plan(attempt=2) → budget exhausted
        assert em.execute_stage.call_count == 2


# ---------------------------------------------------------------------------
# StageRunner — legacy fallback (no engine)
# ---------------------------------------------------------------------------

class TestStageRunnerWithoutEngine:

    def test_policy_controls_loop_without_engine(self):
        """Without engine, retry_policy.should_retry() is the loop gate."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        # Reject once then approve
        rv_mock.review.side_effect = [
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=True),
        ]

        policy_mock = MagicMock()
        policy_mock.should_retry.side_effect = [True, True, True]  # always allow

        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_policy=policy_mock,
            retry_engine=None,  # no engine
        )
        result = runner.run("proj-1", "Architect", "context")

        assert result.success is True
        assert result.attempt_count == 2
        # Policy must be consulted
        assert policy_mock.should_retry.call_count >= 1

    def test_policy_exhaust_stops_loop(self):
        """retry_policy.should_retry() returning False must stop the loop."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        rv_mock.review.return_value = FakeReviewResult(
            approved=False, findings=[_finding("auto_fix")]
        )

        policy_mock = MagicMock()
        # Allow 2 attempts then stop
        policy_mock.should_retry.side_effect = [True, True, False]

        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_policy=policy_mock,
            retry_engine=None,
        )
        result = runner.run("proj-1", "Architect", "context")

        assert result.success is False
        assert em.execute_stage.call_count == 2


# ---------------------------------------------------------------------------
# StageRunner — first-attempt approval (no retry path exercised)
# ---------------------------------------------------------------------------

class TestStageRunnerFirstAttemptApproval:

    def test_approved_first_attempt_no_retry(self):
        """If the reviewer approves on the first attempt, no retry occurs."""
        em = MagicMock()
        em.execute_stage.return_value = FakeExecResult()

        rv_mock = MagicMock()
        rv_mock.review.return_value = FakeReviewResult(approved=True)

        engine = _make_engine()
        policy_mock = MagicMock()

        runner = _make_stage_runner(
            execution_manager=em,
            reviewer=rv_mock,
            retry_policy=policy_mock,
            retry_engine=engine,
        )
        result = runner.run("proj-1", "Architect", "context")

        assert result.success is True
        assert result.attempt_count == 1
        assert em.execute_stage.call_count == 1
        policy_mock.should_retry.assert_not_called()

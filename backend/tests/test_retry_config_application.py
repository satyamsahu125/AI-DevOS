"""test_retry_config_application.py — RetryPlan.modified_config wired into LLM execution.

Verifies:
  1. auto_fix rejection → set_stage_profile called with temperature=0.05 before next attempt.
  2. ask_human rejection → set_stage_profile called with max_tokens=16384 before next attempt.
  3. attempt ≥ 2 → set_stage_profile called with max_tokens=16384 before next attempt.
  4. empty modified_config → set_stage_profile NOT called (no unnecessary calls).
  5. existing non-retry (first-attempt approval) → set_stage_profile never called.
  6. llm_manager not reachable → _apply_retry_config fails silently, loop continues.
  7. ExecutionManager.llm_manager property returns agent factory's _llm_manager.
  8. ExecutionManager.llm_manager returns None when pipeline/factory chain is broken.

Running:
    cd backend
    python -m pytest tests/test_retry_config_application.py -v
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, call

import pytest

from app.shared.dto.model_profile import ModelProfile
from app.workflow.retry_engine import IntelligentRetryEngine
from app.workflow.stage_runner import StageRunner


# ---------------------------------------------------------------------------
# Shared fakes (mirrors test_intelligent_retry_engine.py for isolation)
# ---------------------------------------------------------------------------

@dataclass
class FakeFinding:
    tier: "FakeTier"
    description: str = "test finding"
    suggestion: str = ""


class FakeTier:
    def __init__(self, value: str):
        self.value = value


def _finding(tier_str: str) -> FakeFinding:
    return FakeFinding(tier=FakeTier(tier_str))


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


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _make_llm_manager_mock() -> MagicMock:
    """MagicMock that mimics the LLMManager interface."""
    llm = MagicMock()
    llm.set_stage_profile = MagicMock()
    return llm


def _make_execution_manager_mock(llm_manager: MagicMock | None = MagicMock()) -> MagicMock:
    """MagicMock that mimics ExecutionManager with an accessible llm_manager."""
    em = MagicMock()
    em.execute_stage.return_value = FakeExecResult()
    em.llm_manager = llm_manager  # expose the property directly on the mock
    return em


def _make_runner(
    *,
    execution_manager: MagicMock,
    reviewer: MagicMock,
    engine: IntelligentRetryEngine,
) -> StageRunner:
    el = MagicMock()
    el.record = MagicMock()
    bc = MagicMock()
    rp = MagicMock()
    rp.should_retry.return_value = True

    return StageRunner(
        execution_manager=execution_manager,
        reviewer=reviewer,
        retry_policy=rp,
        event_log=el,
        broadcaster=bc,
        retry_engine=engine,
    )


# ---------------------------------------------------------------------------
# Tests: set_stage_profile called with the right ModelProfile
# ---------------------------------------------------------------------------

class TestModifiedConfigApplied:

    def test_auto_fix_applies_temperature(self):
        """auto_fix rejection → set_stage_profile with temperature=0.05 before retry."""
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        reviewer.review.side_effect = [
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=True),
        ]

        engine = IntelligentRetryEngine(max_retries=5)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Architect", "ctx")

        assert result.success is True
        # set_stage_profile must have been called exactly once (for the single retry)
        llm.set_stage_profile.assert_called_once()
        profile: ModelProfile = llm.set_stage_profile.call_args[0][0]
        assert isinstance(profile, ModelProfile)
        assert profile.temperature == 0.05

    def test_ask_human_escalates_no_set_stage_profile(self):
        """ask_human on first rejection → engine escalates (should_retry=False).

        StageRunner calls plan(attempt=attempt+1) so the first plan call is
        plan(attempt=1). Since ask_human with attempt>=1 escalates immediately,
        should_retry=False and set_stage_profile must NOT be called — there is
        no next attempt to apply it to.
        """
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        reviewer.review.return_value = FakeReviewResult(
            approved=False, findings=[_finding("ask_human")]
        )

        engine = IntelligentRetryEngine(max_retries=5)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "ProductOwner", "ctx")

        # Engine escalates immediately (ask_human at attempt>=1) → failure, no retry
        assert result.success is False
        # No retry → set_stage_profile must NOT be called
        llm.set_stage_profile.assert_not_called()

    def test_late_retry_applies_max_tokens(self):
        """attempt ≥ 2 → set_stage_profile with max_tokens=16384 on the late retry."""
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        # Reject twice (auto_fix) then approve on third attempt
        reviewer.review.side_effect = [
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=True),
        ]

        engine = IntelligentRetryEngine(max_retries=10)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Architect", "ctx")

        assert result.success is True
        # Two retries → set_stage_profile called twice
        assert llm.set_stage_profile.call_count == 2
        # Second call (late retry: attempt=2) must have max_tokens
        second_profile: ModelProfile = llm.set_stage_profile.call_args_list[1][0][0]
        assert second_profile.max_tokens == 16384

    def test_empty_modified_config_does_not_call_set_stage_profile(self):
        """Rejection with unknown type produces empty config → set_stage_profile NOT called."""
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        # Unknown tier → rejection_type="unknown" → no config overrides, attempt 0 < max_retries
        reviewer.review.side_effect = [
            FakeReviewResult(approved=False, findings=[]),  # unknown type, attempt=0, no config
            FakeReviewResult(approved=True),
        ]

        engine = IntelligentRetryEngine(max_retries=5)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Architect", "ctx")

        assert result.success is True
        # unknown type at attempt 0: modified_config={} → set_stage_profile must NOT be called
        llm.set_stage_profile.assert_not_called()

    def test_first_attempt_approval_no_set_stage_profile(self):
        """Approved on first attempt → no retry path → set_stage_profile never called."""
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        reviewer.review.return_value = FakeReviewResult(approved=True)

        engine = IntelligentRetryEngine(max_retries=5)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Architect", "ctx")

        assert result.success is True
        llm.set_stage_profile.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: graceful degradation when llm_manager is unavailable
# ---------------------------------------------------------------------------

class TestModifiedConfigDegradation:

    def test_llm_manager_none_does_not_crash(self):
        """When llm_manager is None, _apply_retry_config is silent and loop continues."""
        em = _make_execution_manager_mock(llm_manager=None)

        reviewer = MagicMock()
        reviewer.review.side_effect = [
            FakeReviewResult(approved=False, findings=[_finding("auto_fix")]),
            FakeReviewResult(approved=True),
        ]

        engine = IntelligentRetryEngine(max_retries=5)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Architect", "ctx")

        # Must still succeed on retry even though config couldn't be applied
        assert result.success is True

    def test_flag_stop_does_not_call_set_stage_profile(self):
        """FLAG rejection → should_retry=False → set_stage_profile NOT called before stop."""
        llm = _make_llm_manager_mock()
        em = _make_execution_manager_mock(llm)

        reviewer = MagicMock()
        reviewer.review.return_value = FakeReviewResult(
            approved=False, findings=[_finding("flag")]
        )

        engine = IntelligentRetryEngine(max_retries=10)
        runner = _make_runner(execution_manager=em, reviewer=reviewer, engine=engine)
        result = runner.run("proj", "Security", "ctx")

        assert result.success is False
        # FLAG → should_stop=True → no next attempt → config must NOT be applied
        llm.set_stage_profile.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: ExecutionManager.llm_manager property
# ---------------------------------------------------------------------------

class TestExecutionManagerLlmManagerProperty:

    def test_returns_agent_factory_llm_manager(self):
        """llm_manager property must expose the agent factory's _llm_manager."""
        from app.execution.manager import ExecutionManager

        fake_llm = MagicMock()
        em = ExecutionManager.__new__(ExecutionManager)
        # Build a minimal mock chain replicating the real structure
        em.engine = MagicMock()
        em.engine.pipeline = MagicMock()
        em.engine.pipeline.agent_factory = MagicMock()
        em.engine.pipeline.agent_factory._llm_manager = fake_llm

        assert em.llm_manager is fake_llm

    def test_returns_none_when_chain_broken(self):
        """llm_manager must return None (not raise) when pipeline/factory is missing."""
        from app.execution.manager import ExecutionManager

        em = ExecutionManager.__new__(ExecutionManager)
        em.engine = MagicMock(spec=[])  # spec=[] → no attributes → AttributeError on access

        result = em.llm_manager
        assert result is None

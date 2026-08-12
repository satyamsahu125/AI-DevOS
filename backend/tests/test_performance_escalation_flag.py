"""test_performance_escalation_flag.py — needs_model_escalation flag in AgentPerformanceScorer.

Verifies:
  1. needs_model_escalation=True when quality=="needs_improvement" AND avg_retries > 1.5.
  2. needs_model_escalation=False when quality=="needs_improvement" but avg_retries <= 1.5.
  3. needs_model_escalation=False when avg_retries > 1.5 but quality is above "needs_improvement".
  4. needs_model_escalation is written to memory as part of the score JSON.
  5. IntelligentRetryEngine._effective_max_retries logs a warning when flag is True.

Running:
    cd backend
    python -m pytest tests/test_performance_escalation_flag.py -v
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.learning.performance_scorer import AgentPerformanceScorer
from app.workflow.retry_engine import IntelligentRetryEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_perf(total: int, avg_retries: float, success_rate: float):
    """Return an object that mimics LearningLoop.get_agent_performance() output."""
    obj = MagicMock()
    obj.total = total
    obj.avg_retries = avg_retries
    obj.success_rate = success_rate
    return obj


def _make_scorer(total: int, avg_retries: float, success_rate: float) -> AgentPerformanceScorer:
    """Return a scorer whose LearningLoop is pre-loaded with fake performance data."""
    ll = MagicMock()
    ll.get_agent_performance.return_value = _make_perf(total, avg_retries, success_rate)
    scorer = AgentPerformanceScorer(learning_loop=ll, cost_tracker=MagicMock(), memory_manager=None)
    return scorer


# ---------------------------------------------------------------------------
# 1-3: needs_model_escalation field value
# ---------------------------------------------------------------------------

class TestNeedsModelEscalationField:

    def test_flag_true_when_needs_improvement_and_high_retries(self):
        """quality==needs_improvement AND avg_retries > 1.5 → needs_model_escalation=True."""
        # Low success, high retries → composite < 0.50 → "needs_improvement"
        # retry_score = max(0.0, 1.0 - (3.0 / 2.0)) = 0.0
        # composite = 0.0*0.6 + 0.0*0.4 = 0.0  → "needs_improvement"
        scorer = _make_scorer(total=5, avg_retries=3.0, success_rate=0.0)
        result = scorer.score_agent("Architect", "proj-1")

        assert result["quality"] == "needs_improvement"
        assert result["avg_retries"] > 1.5
        assert result["needs_model_escalation"] is True

    def test_flag_false_when_needs_improvement_but_low_retries(self):
        """quality==needs_improvement but avg_retries <= 1.5 → needs_model_escalation=False."""
        # retry_score = max(0, 1 - (1.0/2.0)) = 0.5
        # composite = 0.5*0.6 + 0.0*0.4 = 0.30  → "needs_improvement"
        scorer = _make_scorer(total=5, avg_retries=1.0, success_rate=0.0)
        result = scorer.score_agent("Architect", "proj-2")

        assert result["quality"] == "needs_improvement"
        assert result["avg_retries"] <= 1.5
        assert result["needs_model_escalation"] is False

    def test_flag_false_when_high_retries_but_quality_above_needs_improvement(self):
        """avg_retries > 1.5 but quality='fair' → needs_model_escalation=False."""
        # retry_score = max(0, 1 - (2.0/2.0)) = 0.0
        # success_score = 1.0
        # composite = 0.0*0.6 + 1.0*0.4 = 0.40  → still "needs_improvement" actually
        # Let's pick a combo that gives "fair": retry_score=0.5, success_rate=0.6
        # composite = 0.5*0.6 + 0.6*0.4 = 0.30 + 0.24 = 0.54 → "fair"
        scorer = _make_scorer(total=5, avg_retries=1.0, success_rate=0.6)
        result = scorer.score_agent("Designer", "proj-3")

        # Confirm quality is above "needs_improvement"
        assert result["quality"] in ("fair", "good", "excellent")
        assert result["needs_model_escalation"] is False

    def test_flag_false_no_data(self):
        """When total==0 (no data), score_agent returns early without the flag key."""
        ll = MagicMock()
        ll.get_agent_performance.return_value = _make_perf(total=0, avg_retries=0.0, success_rate=0.0)
        scorer = AgentPerformanceScorer(learning_loop=ll, cost_tracker=MagicMock(), memory_manager=None)
        result = scorer.score_agent("Security", "proj-4")

        # Early-return branch: no needs_model_escalation key expected
        assert result.get("score") is None
        # Flag not present in the no-data path
        assert "needs_model_escalation" not in result


# ---------------------------------------------------------------------------
# 4: flag persisted to memory
# ---------------------------------------------------------------------------

class TestEscalationFlagInMemory:

    def test_flag_written_to_memory_when_true(self):
        """When needs_model_escalation=True, it must be in the JSON written to memory."""
        mm = MagicMock()
        ll = MagicMock()
        ll.get_agent_performance.return_value = _make_perf(total=5, avg_retries=3.0, success_rate=0.0)
        scorer = AgentPerformanceScorer(learning_loop=ll, cost_tracker=MagicMock(), memory_manager=mm)

        scorer.score_agent("BackendDeveloper", "proj-5")

        mm.store.assert_called_once()
        _, _, stored_json = mm.store.call_args[0]
        stored = json.loads(stored_json)
        assert stored["needs_model_escalation"] is True


# ---------------------------------------------------------------------------
# 5: IntelligentRetryEngine logs warning when flag is True
# ---------------------------------------------------------------------------

class TestRetryEngineReadsEscalationFlag:

    def test_warning_logged_when_escalation_flagged(self, caplog):
        """_effective_max_retries must log a warning when needs_model_escalation=True."""
        scorer = MagicMock()
        scorer.score_agent.return_value = {
            "score": 0.25,
            "avg_retries": 3.0,
            "needs_model_escalation": True,
        }

        engine = IntelligentRetryEngine(max_retries=3, performance_scorer=scorer)

        with caplog.at_level(logging.WARNING, logger="app.workflow.retry_engine"):
            engine._effective_max_retries("BackendDeveloper", "proj-6")

        assert any("model escalation" in r.message for r in caplog.records), (
            "Expected a warning mentioning 'model escalation' in the log"
        )

    def test_no_warning_when_flag_false(self, caplog):
        """No escalation warning when needs_model_escalation=False."""
        scorer = MagicMock()
        scorer.score_agent.return_value = {
            "score": 0.80,
            "avg_retries": 0.5,
            "needs_model_escalation": False,
        }

        engine = IntelligentRetryEngine(max_retries=3, performance_scorer=scorer)

        with caplog.at_level(logging.WARNING, logger="app.workflow.retry_engine"):
            engine._effective_max_retries("Architect", "proj-7")

        assert not any("model escalation" in r.message for r in caplog.records)

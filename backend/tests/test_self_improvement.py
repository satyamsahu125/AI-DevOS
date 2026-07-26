from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.learning.performance_scorer import AgentPerformanceScorer
from app.learning.prompt_analyzer import PromptQualityAnalyzer

client = TestClient(app)


def test_performance_scorer_no_data():
    mock_ll = MagicMock()
    mock_ll.get_agent_performance.return_value = {"total": 0, "avg_retries": 0.0, "success_rate": 0.0}
    mock_ct = MagicMock()

    scorer = AgentPerformanceScorer(learning_loop=mock_ll, cost_tracker=mock_ct)
    result = scorer.score_agent("architect")
    assert result["score"] is None
    assert result["total_runs"] == 0


def test_performance_scorer_zero_retries_scores_high():
    mock_ll = MagicMock()
    mock_ll.get_agent_performance.return_value = {"total": 10, "avg_retries": 0.0, "success_rate": 1.0}
    mock_ct = MagicMock()

    scorer = AgentPerformanceScorer(learning_loop=mock_ll, cost_tracker=mock_ct)
    score = scorer.score_agent("product_owner")
    assert score["score"] >= 0.85
    assert score["quality"] == "excellent"


def test_performance_scorer_high_retries_scores_low():
    mock_ll = MagicMock()
    mock_ll.get_agent_performance.return_value = {"total": 10, "avg_retries": 2.0, "success_rate": 0.6}
    mock_ct = MagicMock()

    scorer = AgentPerformanceScorer(learning_loop=mock_ll, cost_tracker=mock_ct)
    score = scorer.score_agent("backend")
    assert score["score"] < 0.5
    assert score["quality"] == "needs_improvement"


def test_prompt_analyzer_no_lessons():
    mock_ls = MagicMock()
    mock_ls.get_all_lessons.return_value = []
    mock_km = MagicMock()

    analyzer = PromptQualityAnalyzer(lesson_store=mock_ls, knowledge_memory=mock_km)
    result = analyzer.analyze_stage("architect")
    assert "No lessons yet" in result["message"]


def test_learning_performance_endpoint():
    res = client.get("/api/learning/performance")
    assert res.status_code == 200
    assert "scores" in res.json()


def test_learning_insights_endpoint():
    res = client.get("/api/learning/insights/architect")
    assert res.status_code == 200
    assert "stage" in res.json()


def test_patterns_endpoint():
    res = client.get("/api/learning/patterns?query=build+a+todo+app")
    assert res.status_code == 200
    assert "patterns" in res.json()

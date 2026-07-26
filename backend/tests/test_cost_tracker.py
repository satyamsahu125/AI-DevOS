from fastapi.testclient import TestClient
from app.main import app
from app.llm.cost_tracker import CostTracker

client = TestClient(app)


def test_cost_tracker_records_call():
    tracker = CostTracker(":memory:")
    tracker.record(
        project_id="proj-1",
        stage="architect",
        provider="ollama",
        model="qwen2.5-coder:7b",
        prompt_tokens=1000,
        completion_tokens=500,
        latency_ms=3200,
        success=True,
    )
    summary = tracker.get_project_summary("proj-1")
    assert summary.total_llm_calls == 1
    assert summary.total_tokens == 1500


def test_cost_tracker_multiple_stages():
    tracker = CostTracker(":memory:")
    for stage in ["product_owner", "architect", "backend"]:
        tracker.record(
            project_id="proj-1",
            stage=stage,
            provider="ollama",
            model="qwen2.5-coder:7b",
            prompt_tokens=800,
            completion_tokens=400,
            latency_ms=2000,
            success=True,
        )
    summary = tracker.get_project_summary("proj-1")
    assert summary.total_llm_calls == 3
    assert len(summary.stages) == 3


def test_cost_tracker_free_for_ollama():
    tracker = CostTracker(":memory:")
    tracker.record(
        project_id="proj-1",
        stage="backend",
        provider="ollama",
        model="qwen2.5-coder:7b",
        prompt_tokens=10000,
        completion_tokens=5000,
        latency_ms=5000,
        success=True,
    )
    summary = tracker.get_project_summary("proj-1")
    assert summary.estimated_cost_usd == 0.0


def test_cost_tracker_tracks_retries():
    tracker = CostTracker(":memory:")
    for _ in range(2):
        tracker.record(
            project_id="proj-1",
            stage="architect",
            provider="ollama",
            model="qwen2.5-coder:7b",
            prompt_tokens=500,
            completion_tokens=300,
            latency_ms=2000,
            success=True,
        )
    summary = tracker.get_project_summary("proj-1")
    stage = summary.stages[0]
    assert stage.llm_calls == 2
    assert stage.retries == 1


def test_metrics_endpoint_returns_200():
    res = client.get("/api/projects/test-id/metrics")
    assert res.status_code == 200

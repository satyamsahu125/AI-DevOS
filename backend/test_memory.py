import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.memory.memory_manager import MemoryOrchestrator
from app.memory.learning_loop import LearningLoop, Trajectory
from datetime import datetime, timezone
import json

def test_memory():
    print("Testing Memory and Learning Loop...")
    # Clean up previous db
    db_path = Path("data/learning.sqlite")
    if db_path.exists():
        db_path.unlink()
    
    loop = LearningLoop(db_path=db_path)
    
    print("1. Injecting a failed trajectory...")
    t_failed = Trajectory(
        stage="ProductOwner",
        task_description="Build a social media app",
        artifact_summary="Output was too short.",
        retry_count=1,
        approved=False,
        reviewer_feedback="You must include at least 3 user stories. Your output only had 1.",
        agent_model="stub",
        tokens_used=100,
        latency_ms=1000,
        project_id="test-proj-1",
    )
    loop.record_trajectory(t_failed)
    
    print("2. Injecting a successful trajectory with lessons...")
    t_success = Trajectory(
        stage="ProductOwner",
        task_description="Build a social media app",
        artifact_summary="Output contains 5 user stories.",
        retry_count=2,
        approved=True,
        reviewer_feedback="Great, you included 5 user stories.",
        agent_model="stub",
        tokens_used=500,
        latency_ms=2000,
        project_id="test-proj-1",
    )
    loop.record_trajectory(t_success)
    
    print("3. Querying relevant patterns...")
    patterns = loop.get_relevant_patterns("Build a social media app", "ProductOwner", project_id="test-proj-1")
    print(f"Retrieved {len(patterns)} patterns.")
    for p in patterns:
        print(f" - {p}")
        
    assert len(patterns) > 0, "No patterns retrieved!"
    assert "user stories" in patterns[0].lower(), "Pattern did not contain expected lesson."
    print("Memory verification passed!")

if __name__ == "__main__":
    test_memory()

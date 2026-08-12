"""test_phase9_template_impact.py — P9-2b: Template Pipeline Repair & Observability.

Verifies:
  A. Bug fix: find_similar receives limit=1, not top_n
  B. Context propagation: richer ctx_dict reaches TemplateEngine
  C. Schema: template_injected column exists with default 0
  D. Injection propagation: template_injected flows end-to-end to SQLite
  E. Project/stage isolation: no shared mutable state
  F. min_similarity: threshold filtering and combination with limit
  G. Analytics: /analytics/template-impact endpoint

Running:
    cd backend
    python -m pytest tests/test_phase9_template_impact.py -v
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template_engine(tmp_path: Path):
    from app.learning.template_engine import TemplateEngine
    return TemplateEngine(db_path=tmp_path / "templates.sqlite")


def _make_learning_loop(tmp_path: Path):
    """Return a LearningLoop with a no-op KnowledgeMemory so embedding is skipped."""
    from app.memory.learning_loop import LearningLoop
    km = MagicMock()
    km.store = MagicMock()
    km.search = MagicMock(return_value=[])
    return LearningLoop(db_path=tmp_path / "learning.sqlite", knowledge_memory=km)


def _make_stage_ctx_mock(prompt_dict: dict):
    """Return a MagicMock that behaves like StageContext."""
    ctx = MagicMock()
    ctx.to_prompt_dict.return_value = dict(prompt_dict)
    return ctx


def _make_review_result(approved: bool = True):
    rr = MagicMock()
    rr.approved = approved
    rr.overall_feedback = "looks good" if approved else "needs work"
    return rr


# ---------------------------------------------------------------------------
# A. Bug fix
# ---------------------------------------------------------------------------

class TestBugFix:
    """find_similar must receive limit=1, never top_n."""

    def test_find_similar_called_with_limit_not_top_n(self, tmp_path):
        """_inject_template must call find_similar with limit=1, not top_n."""
        from app.workflow.context_assembler import ContextAssembler

        te = MagicMock()
        te.find_similar.return_value = []  # no templates → no injection

        assembler = ContextAssembler(template_engine=te)
        assembler._inject_template("BackendDeveloper", "proj-1", "some context")

        # Must NOT have been called with top_n at all
        for c in te.find_similar.call_args_list:
            assert "top_n" not in c.kwargs, "top_n keyword must not appear in find_similar call"
        # Must have been called with limit
        te.find_similar.assert_called_once()
        _, kwargs = te.find_similar.call_args
        assert "limit" in kwargs or len(te.find_similar.call_args.args) >= 3

    def test_injection_succeeds_when_template_exists(self, tmp_path):
        """When a matching template exists, injection must return augmented content and True."""
        from app.workflow.context_assembler import ContextAssembler

        te = _make_template_engine(tmp_path)
        # Insert a template for the stage
        artifact = {"endpoints": [{"method": "POST", "path": "/users"}], "models": ["User"]}
        te.extract_template(artifact, stage="BackendDeveloper", project_id="seed-proj")

        assembler = ContextAssembler(template_engine=te)
        context_hint = {"architecture_artifact": {"components": ["UserService"]}}
        augmented, injected = assembler._inject_template(
            "BackendDeveloper", "proj-1", "base context", context_hint=context_hint,
        )
        assert injected is True
        assert "STRUCTURAL TEMPLATE" in augmented
        assert "base context" in augmented

    def test_no_injection_when_no_templates(self, tmp_path):
        """When no templates exist for a stage, content is unchanged and flag is False."""
        from app.workflow.context_assembler import ContextAssembler

        te = _make_template_engine(tmp_path)
        assembler = ContextAssembler(template_engine=te)
        original = "original context"
        result, injected = assembler._inject_template("UnknownStage", "proj-x", original)
        assert injected is False
        assert result == original

    def test_no_injection_when_no_template_engine(self):
        """Without a template engine wired, injection returns content unchanged and False."""
        from app.workflow.context_assembler import ContextAssembler

        assembler = ContextAssembler(template_engine=None)
        result, injected = assembler._inject_template("Architect", "proj-1", "ctx")
        assert injected is False
        assert result == "ctx"

    def test_inject_template_exception_yields_false_not_raise(self, tmp_path):
        """An exception inside _inject_template must be swallowed and return False."""
        from app.workflow.context_assembler import ContextAssembler

        te = MagicMock()
        te.find_similar.side_effect = RuntimeError("db exploded")
        assembler = ContextAssembler(template_engine=te)
        result, injected = assembler._inject_template("Architect", "proj-1", "ctx")
        assert injected is False
        assert result == "ctx"


# ---------------------------------------------------------------------------
# B. Context propagation
# ---------------------------------------------------------------------------

class TestContextPropagation:
    """ctx_dict from orchestrator path must reach TemplateEngine.find_similar."""

    def test_orchestrator_ctx_dict_passed_to_find_similar(self, tmp_path):
        """The rich prompt dict from to_prompt_dict() must arrive at find_similar."""
        from app.workflow.context_assembler import ContextAssembler

        rich_dict = {
            "original_request": "build a REST API",
            "architecture_artifact": {"components": ["UserService", "AuthService"]},
            "design_artifact": {"screens": ["LoginPage"]},
        }

        mock_mo = MagicMock()
        mock_mo.get_context.return_value = _make_stage_ctx_mock(rich_dict)

        te = MagicMock()
        te.find_similar.return_value = []

        assembler = ContextAssembler(memory_orchestrator=mock_mo, template_engine=te)
        assembler.assemble("proj-1", "BackendDeveloper", "")

        # find_similar must have been called exactly once
        te.find_similar.assert_called_once()
        call_args = te.find_similar.call_args
        # Second positional arg (or context kwarg) must be the rich dict, not 2-key fallback
        similarity_context = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("context", {})
        assert "architecture_artifact" in similarity_context or "original_request" in similarity_context, (
            f"Expected rich ctx_dict but got: {similarity_context}"
        )

    def test_caller_context_preserved_in_similarity_dict(self, tmp_path):
        """When caller_context is provided, it must appear in the dict passed to find_similar."""
        from app.workflow.context_assembler import ContextAssembler

        mock_mo = MagicMock()
        mock_mo.get_context.return_value = _make_stage_ctx_mock({"original_request": "test"})

        te = MagicMock()
        te.find_similar.return_value = []

        assembler = ContextAssembler(memory_orchestrator=mock_mo, template_engine=te)
        assembler.assemble("proj-1", "BackendDeveloper", "sprint goal: build auth")

        call_args = te.find_similar.call_args
        similarity_context = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("context", {})
        # caller_context must be merged into the ctx_dict
        assert "caller_context" in similarity_context

    def test_legacy_path_still_works_without_orchestrator(self, tmp_path):
        """Without a memory_orchestrator, assemble must not raise and still return AssembleResult."""
        from app.workflow.context_assembler import AssembleResult, ContextAssembler

        assembler = ContextAssembler(memory_orchestrator=None, template_engine=None)
        result = assembler.assemble("proj-1", "Architect", "build something")
        assert isinstance(result, AssembleResult)
        assert isinstance(result.context, str)
        assert result.template_injected is False

    def test_no_second_get_context_call(self):
        """_inject_template must NOT trigger a second get_context() call."""
        from app.workflow.context_assembler import ContextAssembler

        mock_mo = MagicMock()
        mock_mo.get_context.return_value = _make_stage_ctx_mock({"original_request": "x"})

        te = MagicMock()
        te.find_similar.return_value = []

        assembler = ContextAssembler(memory_orchestrator=mock_mo, template_engine=te)
        assembler.assemble("proj-1", "Architect", "")

        # get_context must be called exactly once — not a second time for template hint
        assert mock_mo.get_context.call_count == 1

    def test_assemble_result_type(self):
        """assemble() must return AssembleResult, not a plain str."""
        from app.workflow.context_assembler import AssembleResult, ContextAssembler

        mock_mo = MagicMock()
        mock_mo.get_context.return_value = _make_stage_ctx_mock({"original_request": "x"})

        assembler = ContextAssembler(memory_orchestrator=mock_mo, template_engine=None)
        result = assembler.assemble("proj-1", "Architect", "")
        assert isinstance(result, AssembleResult)
        assert isinstance(result.context, str)
        assert isinstance(result.template_injected, bool)

    def test_legacy_fallback_uses_minimal_context(self):
        """Legacy path must fall back to {project_id, stage} context dict for find_similar."""
        from app.workflow.context_assembler import ContextAssembler

        te = MagicMock()
        te.find_similar.return_value = []

        # No orchestrator → legacy path → minimal fallback context
        assembler = ContextAssembler(memory_orchestrator=None, template_engine=te)
        assembler.assemble("proj-legacy", "Architect", "")

        call_args = te.find_similar.call_args
        context_passed = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("context", {})
        assert "project_id" in context_passed
        assert context_passed["project_id"] == "proj-legacy"


# ---------------------------------------------------------------------------
# C. Schema
# ---------------------------------------------------------------------------

class TestSchema:
    """template_injected column must exist with default 0."""

    def test_template_injected_column_exists(self, tmp_path):
        """After init, trajectories table must have template_injected column."""
        ll = _make_learning_loop(tmp_path)
        cursor = ll._conn.execute("PRAGMA table_info(trajectories)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "template_injected" in columns

    def test_template_injected_default_is_zero(self, tmp_path):
        """Rows inserted without template_injected must default to 0."""
        ll = _make_learning_loop(tmp_path)
        # Insert a row using the low-level connection to bypass Python-level defaults
        ll._conn.execute(
            """INSERT INTO trajectories
               (project_id, stage, task_description, artifact_summary, retry_count,
                approved, reviewer_feedback, agent_model, tokens_used, latency_ms, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("p1", "Architect", "task", "summary", 0, 1, "", "model", 100, 50.0,
             datetime.now(timezone.utc).isoformat()),
        )
        ll._conn.commit()
        row = ll._conn.execute("SELECT template_injected FROM trajectories").fetchone()
        assert row is not None
        assert row[0] == 0

    def test_existing_database_initializes_successfully(self, tmp_path):
        """An existing DB without the column must gain it via ALTER TABLE without errors."""
        db_path = tmp_path / "old.sqlite"
        # Create DB without template_injected column (simulates pre-P9-2b schema)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL,
                task_description TEXT NOT NULL,
                artifact_summary TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                approved INTEGER NOT NULL,
                reviewer_feedback TEXT NOT NULL,
                agent_model TEXT NOT NULL,
                tokens_used INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                recorded_at TEXT NOT NULL
            )"""
        )
        conn.commit()
        conn.close()

        # LearningLoop init must add the missing column without raising
        from app.memory.learning_loop import LearningLoop
        ll = LearningLoop(db_path=db_path)
        cursor = ll._conn.execute("PRAGMA table_info(trajectories)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "template_injected" in columns


# ---------------------------------------------------------------------------
# D. Injection propagation end-to-end
# ---------------------------------------------------------------------------

class TestInjectionPropagation:
    """template_injected must flow from ContextAssembler → LearningMiddleware → SQLite."""

    def test_injected_trajectory_written_with_true(self, tmp_path):
        """When injection succeeds, the trajectory row must have template_injected=1."""
        from app.memory.learning_loop import LearningLoop, Trajectory

        ll = _make_learning_loop(tmp_path)
        t = Trajectory(
            stage="BackendDeveloper",
            task_description="build API",
            artifact_summary="artifact",
            retry_count=0,
            approved=True,
            reviewer_feedback="good",
            agent_model="test-model",
            tokens_used=500,
            latency_ms=100.0,
            project_id="proj-1",
            template_injected=True,
        )
        ll.record_trajectory(t)

        row = ll._conn.execute(
            "SELECT template_injected FROM trajectories WHERE project_id=?", ("proj-1",)
        ).fetchone()
        assert row is not None
        assert row[0] == 1

    def test_non_injected_trajectory_written_with_false(self, tmp_path):
        """Without injection, template_injected column must be 0."""
        from app.memory.learning_loop import LearningLoop, Trajectory

        ll = _make_learning_loop(tmp_path)
        t = Trajectory(
            stage="Architect",
            task_description="design system",
            artifact_summary="arch doc",
            retry_count=0,
            approved=True,
            reviewer_feedback="approved",
            agent_model="model",
            tokens_used=200,
            latency_ms=50.0,
            project_id="proj-2",
            template_injected=False,
        )
        ll.record_trajectory(t)

        row = ll._conn.execute(
            "SELECT template_injected FROM trajectories WHERE project_id=?", ("proj-2",)
        ).fetchone()
        assert row[0] == 0

    def test_learning_middleware_records_template_injected(self, tmp_path):
        """LearningMiddleware.on_attempt must write template_injected to the trajectory."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, llm_model="test-model")

        artifact = MagicMock()
        artifact.content = "API implementation"
        rr = _make_review_result(approved=True)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            t = MagicMock()
            t.last_call_tokens = 100
            t.last_call_latency = 50.0
            mock_tracker.return_value = t
            mw.on_attempt(
                "BackendDeveloper", "proj-mw", "build", 1, artifact, rr,
                template_injected=True,
            )

        row = ll._conn.execute(
            "SELECT template_injected FROM trajectories WHERE project_id=?", ("proj-mw",)
        ).fetchone()
        assert row is not None
        assert row[0] == 1

    def test_learning_middleware_default_false(self, tmp_path):
        """on_attempt with no template_injected arg defaults to False."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, llm_model="m")

        artifact = MagicMock()
        artifact.content = "output"
        rr = _make_review_result(approved=False)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            t = MagicMock()
            t.last_call_tokens = 10
            t.last_call_latency = 5.0
            mock_tracker.return_value = t
            mw.on_attempt("Architect", "proj-def", "task", 0, artifact, rr)

        row = ll._conn.execute(
            "SELECT template_injected FROM trajectories WHERE project_id=?", ("proj-def",)
        ).fetchone()
        assert row[0] == 0

    def test_assemble_result_template_injected_propagates(self, tmp_path):
        """AssembleResult.template_injected=True must be carried into _on_attempt."""
        from app.workflow.context_assembler import ContextAssembler, AssembleResult

        # Mock assembler that reports injection happened
        mock_assembler = MagicMock(spec=ContextAssembler)
        mock_assembler.assemble.return_value = AssembleResult(
            context='{"original_request": "build"}',
            template_injected=True,
        )

        captured: list[dict] = []

        class _CaptureMW:
            def on_attempt(self, *args, template_injected=False, **kwargs):
                captured.append({"template_injected": template_injected})

            def on_approval(self, *args, **kwargs):
                pass

        from app.workflow.engine import WorkflowEngine

        # Build a minimal WorkflowEngine with controlled collaborators.
        # The StageRunner mock must invoke on_attempt so the middleware records the trajectory.
        fake_artifact = MagicMock()
        fake_artifact.content = "output"
        fake_review = _make_review_result(approved=False)

        def _fake_stage_run(project_id, stage_name, context, on_attempt=None):
            if on_attempt is not None:
                on_attempt(0, fake_artifact, fake_review)
            result = MagicMock()
            result.success = False
            result.stopped = False
            result.message = "failed"
            result.artifact = None
            result.attempt_count = 1
            result.review_result = fake_review
            result.failed_approaches = []
            result.duration_sec = 1.0
            return result

        mock_stage_runner = MagicMock()
        mock_stage_runner.run.side_effect = _fake_stage_run

        engine = WorkflowEngine(
            stage_runner=mock_stage_runner,
            context_assembler=mock_assembler,
            learning_middleware=_CaptureMW(),
        )
        # Patch post-approval helpers that touch disk
        with patch.object(engine, "_checkpoint", MagicMock()), \
             patch.object(engine, "session_manager", MagicMock()), \
             patch.object(engine, "_apply_model_router_profile", MagicMock()), \
             patch.object(engine, "execution_manager", MagicMock()), \
             patch.object(engine, "_update_project_failure", MagicMock()):
            engine.run("proj-1", "BackendDeveloper", "build an API")

        assert len(captured) >= 1
        assert captured[0]["template_injected"] is True


# ---------------------------------------------------------------------------
# E. Project / stage isolation
# ---------------------------------------------------------------------------

class TestIsolation:
    """Injection status must be per-execution, not shared across runs."""

    def test_two_executions_independent_injection_status(self, tmp_path):
        """Two trajectories for different projects must have independent template_injected."""
        from app.memory.learning_loop import LearningLoop, Trajectory

        ll = _make_learning_loop(tmp_path)

        def _record(project_id: str, injected: bool):
            ll.record_trajectory(Trajectory(
                stage="Architect", task_description="t", artifact_summary="s",
                retry_count=0, approved=True, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id=project_id, template_injected=injected,
            ))

        _record("proj-injected", True)
        _record("proj-not-injected", False)

        rows = ll._conn.execute(
            "SELECT project_id, template_injected FROM trajectories ORDER BY project_id"
        ).fetchall()
        assert len(rows) == 2
        by_proj = {r[0]: r[1] for r in rows}
        assert by_proj["proj-injected"] == 1
        assert by_proj["proj-not-injected"] == 0

    def test_no_instance_state_on_context_assembler(self, tmp_path):
        """ContextAssembler must not use instance variables to carry injection state."""
        from app.workflow.context_assembler import ContextAssembler
        import inspect

        # Verify _inject_template returns a tuple (stateless design)
        te = _make_template_engine(tmp_path)
        te.extract_template({"k": "v"}, stage="Architect", project_id="seed")

        assembler = ContextAssembler(template_engine=te)
        # Both calls must be independent — no leakage between them
        _, injected_1 = assembler._inject_template("Architect", "proj-a", "ctx")
        _, injected_2 = assembler._inject_template("NoSuchStage", "proj-b", "ctx")

        assert injected_1 is True
        assert injected_2 is False


# ---------------------------------------------------------------------------
# F. min_similarity
# ---------------------------------------------------------------------------

class TestMinSimilarity:
    """find_similar min_similarity threshold must filter correctly."""

    def _make_engine_with_templates(self, tmp_path: Path):
        te = _make_template_engine(tmp_path)
        # High-overlap artifact: shares endpoint/auth/models keys with the query below
        te.extract_template(
            {"endpoints": "x", "auth": "x", "models": "x", "tests": "x"},
            stage="BackendDeveloper",
        )
        # Zero-overlap artifact: completely different keys
        te.extract_template(
            {"unrelated_key_1": "x", "unrelated_key_2": "x"},
            stage="BackendDeveloper",
        )
        return te

    def test_result_below_threshold_excluded(self, tmp_path):
        """A template whose Jaccard score is 0.0 must be excluded at any threshold > 0."""
        te = _make_template_engine(tmp_path)
        # Store a template with completely different keys from the query context
        te.extract_template({"alpha": "x", "beta": "x"}, stage="TestStage")

        # Query with no overlapping keys → score 0.0
        results = te.find_similar("TestStage", {"gamma": "x", "delta": "x"}, min_similarity=0.1)
        assert results == []

    def test_result_at_threshold_included(self, tmp_path):
        """A template whose score equals min_similarity must be included (inclusive)."""
        te = _make_template_engine(tmp_path)
        # Template key "shared"; context key "shared" → Jaccard = 1/1 = 1.0
        te.extract_template({"shared": "x"}, stage="TestStage")

        results = te.find_similar("TestStage", {"shared": "val"}, min_similarity=1.0)
        assert len(results) == 1

    def test_result_above_threshold_included(self, tmp_path):
        """Templates above min_similarity must be returned."""
        te = self._make_engine_with_templates(tmp_path)
        query = {"endpoints": "POST /users", "auth": "JWT", "models": "User", "tests": "pytest"}
        # High overlap template must survive threshold 0.1
        results = te.find_similar("BackendDeveloper", query, min_similarity=0.1, limit=5)
        assert len(results) >= 1

    def test_limit_applied_after_threshold(self, tmp_path):
        """limit restricts the count of qualifying results after threshold filtering."""
        te = _make_template_engine(tmp_path)
        for i in range(10):
            te.extract_template({"k": str(i)}, stage="LimitStage")

        # All templates share the "k" key with the query → score > 0
        results = te.find_similar("LimitStage", {"k": "anything"}, limit=3, min_similarity=0.0)
        assert len(results) <= 3

    def test_default_min_similarity_is_zero(self, tmp_path):
        """Default min_similarity=0.0 must return all templates regardless of score."""
        te = _make_template_engine(tmp_path)
        te.extract_template({"alpha": "x"}, stage="DefaultStage")
        te.extract_template({"beta": "x"}, stage="DefaultStage")

        # Query has no overlap with either → scores = 0.0
        results = te.find_similar("DefaultStage", {"gamma": "x"})
        # Both templates must be returned (no threshold)
        assert len(results) == 2

    def test_invalid_min_similarity_raises(self, tmp_path):
        """min_similarity outside [0.0, 1.0] must raise ValueError."""
        te = _make_template_engine(tmp_path)
        with pytest.raises(ValueError, match="min_similarity"):
            te.find_similar("AnyStage", {}, min_similarity=1.5)
        with pytest.raises(ValueError, match="min_similarity"):
            te.find_similar("AnyStage", {}, min_similarity=-0.1)


# ---------------------------------------------------------------------------
# G. Analytics endpoint
# ---------------------------------------------------------------------------

class TestTemplateImpactAnalytics:
    """GET /analytics/template-impact must return correct schema and data."""

    def _make_client_with_ll(self, ll):
        """Build a TestClient with _get_learning_loop patched to return ll."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            yield client

    def test_endpoint_exists(self, tmp_path):
        """GET /analytics/template-impact must return HTTP 200."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        app = FastAPI()
        app.include_router(analytics_mod.router)
        ll = _make_learning_loop(tmp_path)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")
        assert resp.status_code == 200

    def test_response_schema_keys(self, tmp_path):
        """Response must contain stage_filter, stages, total_injected, total_non_injected."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        app = FastAPI()
        app.include_router(analytics_mod.router)
        ll = _make_learning_loop(tmp_path)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        data = resp.json()
        for key in ("stage_filter", "stages", "total_injected", "total_non_injected"):
            assert key in data, f"Missing key: {key}"

    def test_zero_data_deterministic(self, tmp_path):
        """Empty DB must return deterministic zero-count response."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        app = FastAPI()
        app.include_router(analytics_mod.router)
        ll = _make_learning_loop(tmp_path)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        data = resp.json()
        assert data["stages"] == []
        assert data["total_injected"] == 0
        assert data["total_non_injected"] == 0

    def test_injected_non_injected_counts_correct(self, tmp_path):
        """Injected and non-injected counts must match the recorded trajectories."""
        from app.memory.learning_loop import LearningLoop, Trajectory
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        ll = _make_learning_loop(tmp_path)
        stage = "BackendDeveloper"

        def _record(injected: bool, approved: bool):
            ll.record_trajectory(Trajectory(
                stage=stage, task_description="t", artifact_summary="s",
                retry_count=0, approved=approved, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id="p1", template_injected=injected,
            ))

        _record(True, True)
        _record(True, False)
        _record(False, True)
        _record(False, True)
        _record(False, False)

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        data = resp.json()
        assert data["total_injected"] == 2
        assert data["total_non_injected"] == 3

        entry = next((e for e in data["stages"] if e["stage"] == stage), None)
        assert entry is not None
        assert entry["injected_count"] == 2
        assert entry["non_injected_count"] == 3
        assert entry["injected_approved"] == 1
        assert entry["non_injected_approved"] == 2

    def test_approval_rates_correct(self, tmp_path):
        """Approval rates must be computed correctly from injected/non-injected runs."""
        from app.memory.learning_loop import LearningLoop, Trajectory
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        ll = _make_learning_loop(tmp_path)

        # 2 injected: 2 approved → rate = 1.0
        for _ in range(2):
            ll.record_trajectory(Trajectory(
                stage="Architect", task_description="t", artifact_summary="s",
                retry_count=0, approved=True, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id="p", template_injected=True,
            ))
        # 4 non-injected: 1 approved → rate = 0.25
        for approved in [True, False, False, False]:
            ll.record_trajectory(Trajectory(
                stage="Architect", task_description="t", artifact_summary="s",
                retry_count=0, approved=approved, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id="p", template_injected=False,
            ))

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        entry = next(e for e in resp.json()["stages"] if e["stage"] == "Architect")
        assert entry["injected_approval_rate"] == 1.0
        assert entry["non_injected_approval_rate"] == pytest.approx(0.25, abs=0.001)

    def test_stage_filter(self, tmp_path):
        """stage query parameter must restrict results to that stage only."""
        from app.memory.learning_loop import LearningLoop, Trajectory
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        ll = _make_learning_loop(tmp_path)
        for stage in ("Architect", "BackendDeveloper"):
            ll.record_trajectory(Trajectory(
                stage=stage, task_description="t", artifact_summary="s",
                retry_count=0, approved=True, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id="p", template_injected=True,
            ))

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact?stage=Architect")

        data = resp.json()
        assert data["stage_filter"] == "Architect"
        assert len(data["stages"]) == 1
        assert data["stages"][0]["stage"] == "Architect"

    def test_no_sensitive_data_in_response(self, tmp_path):
        """Response must not expose task_description, reviewer_feedback, or credentials."""
        from app.memory.learning_loop import LearningLoop, Trajectory
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        ll = _make_learning_loop(tmp_path)
        ll.record_trajectory(Trajectory(
            stage="Security", task_description="SECRET TASK",
            artifact_summary="secret artifact", retry_count=0, approved=True,
            reviewer_feedback="SECRET FEEDBACK", agent_model="model",
            tokens_used=100, latency_ms=10.0, project_id="p", template_injected=True,
        ))

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=ll), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        raw = resp.text
        assert "SECRET TASK" not in raw
        assert "SECRET FEEDBACK" not in raw
        assert "secret artifact" not in raw

    def test_no_learning_loop_returns_empty_response(self, tmp_path):
        """When DI container has no learning loop, endpoint must return empty data without error."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import analytics as analytics_mod

        app = FastAPI()
        app.include_router(analytics_mod.router)

        with patch.object(analytics_mod, "_get_learning_loop", return_value=None), \
             patch.object(analytics_mod, "get_shared_cost_tracker", return_value=MagicMock()):
            client = TestClient(app)
            resp = client.get("/analytics/template-impact")

        assert resp.status_code == 200
        data = resp.json()
        assert data["stages"] == []
        assert data["total_injected"] == 0

    def test_get_template_impact_stage_isolation(self, tmp_path):
        """get_template_impact(stage=X) must not include other stages."""
        ll = _make_learning_loop(tmp_path)
        from app.memory.learning_loop import Trajectory

        for stage, injected in [("Architect", True), ("Designer", False), ("Architect", False)]:
            ll.record_trajectory(Trajectory(
                stage=stage, task_description="t", artifact_summary="s",
                retry_count=0, approved=True, reviewer_feedback="",
                agent_model="m", tokens_used=100, latency_ms=10.0,
                project_id="p", template_injected=injected,
            ))

        entries = ll.get_template_impact(stage="Architect")
        assert len(entries) == 1
        assert entries[0]["stage"] == "Architect"
        assert entries[0]["injected_count"] == 1
        assert entries[0]["non_injected_count"] == 1

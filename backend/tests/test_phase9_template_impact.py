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
        res = assembler._inject_template(
            "BackendDeveloper", "proj-1", "base context", context_hint=context_hint,
        )
        augmented, injected = res[0], res[1]
        assert injected is True
        assert "STRUCTURAL TEMPLATE" in augmented
        assert "base context" in augmented

    def test_no_injection_when_no_templates(self, tmp_path):
        """When no templates exist for a stage, content is unchanged and flag is False."""
        from app.workflow.context_assembler import ContextAssembler

        te = _make_template_engine(tmp_path)
        assembler = ContextAssembler(template_engine=te)
        original = "original context"
        res = assembler._inject_template("UnknownStage", "proj-x", original)
        result, injected = res[0], res[1]
        assert injected is False
        assert result == original

    def test_no_injection_when_no_template_engine(self):
        """Without a template engine wired, injection returns content unchanged and False."""
        from app.workflow.context_assembler import ContextAssembler

        assembler = ContextAssembler(template_engine=None)
        res = assembler._inject_template("Architect", "proj-1", "ctx")
        result, injected = res[0], res[1]
        assert injected is False
        assert result == "ctx"

    def test_inject_template_exception_yields_false_not_raise(self, tmp_path):
        """An exception inside _inject_template must be swallowed and return False."""
        from app.workflow.context_assembler import ContextAssembler

        te = MagicMock()
        te.find_similar.side_effect = RuntimeError("db exploded")
        assembler = ContextAssembler(template_engine=te)
        res = assembler._inject_template("Architect", "proj-1", "ctx")
        result, injected = res[0], res[1]
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
        res1 = assembler._inject_template("Architect", "proj-a", "ctx")
        res2 = assembler._inject_template("NoSuchStage", "proj-b", "ctx")
        injected_1 = res1[1]
        injected_2 = res2[1]

        assert injected_1 is True
        assert injected_2 is False




# ---------------------------------------------------------------------------
# F. min_similarity
# ---------------------------------------------------------------------------

class TestDeterministicStageSelection:
    """Phase A: find_similar performs deterministic stage match + recency selection."""

    def test_min_similarity_param_does_not_alter_selection(self, tmp_path: Path):
        """min_similarity param is preserved for API compatibility but does not alter selection."""
        te = _make_template_engine(tmp_path)
        te.extract_template({"alpha": "x"}, stage="TestStage")

        # Query with min_similarity returns the stage template deterministically
        results_0 = te.find_similar("TestStage", {"gamma": "x"}, min_similarity=0.0)
        results_1 = te.find_similar("TestStage", {"gamma": "x"}, min_similarity=0.9)
        assert len(results_0) == 1
        assert len(results_1) == 1
        assert results_0[0].template_id == results_1[0].template_id

    def test_context_contents_do_not_alter_ordering(self, tmp_path: Path):
        """Different contexts return the exact same deterministic template order."""
        te = _make_template_engine(tmp_path)
        te.extract_template({"older": "1"}, stage="TestStage")
        te.extract_template({"newer": "2"}, stage="TestStage")

        res_a = te.find_similar("TestStage", {"context_a": "val"})
        res_b = te.find_similar("TestStage", {"completely_different": "val"})

        assert [t.template_id for t in res_a] == [t.template_id for t in res_b]
        assert "newer" in res_a[0].structure

    def test_limit_applied_to_results(self, tmp_path: Path):
        """limit restricts the count of returned templates for the stage."""
        te = _make_template_engine(tmp_path)
        for i in range(10):
            te.extract_template({"k": str(i)}, stage="LimitStage")

        results = te.find_similar("LimitStage", {"k": "anything"}, limit=3)
        assert len(results) == 3

    def test_stage_filtering_mandatory(self, tmp_path: Path):
        """Only templates matching the requested stage are returned."""
        te = _make_template_engine(tmp_path)
        te.extract_template({"backend": "x"}, stage="BackendDeveloper")
        te.extract_template({"frontend": "x"}, stage="FrontendDeveloper")

        results = te.find_similar("BackendDeveloper", {})
        assert len(results) == 1
        assert results[0].stage == "BackendDeveloper"


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


# ---------------------------------------------------------------------------
# H. Phase B Telemetry Attribution
# ---------------------------------------------------------------------------

class TestPhaseBTelemetryAttribution:
    """P9-2b Phase B: Telemetry & Observability Attribution."""

    def test_schema_columns_exist(self, tmp_path):
        """trajectories and templates tables must contain Phase B telemetry columns."""
        ll = _make_learning_loop(tmp_path)
        te = _make_template_engine(tmp_path)

        cursor_traj = ll._conn.execute("PRAGMA table_info(trajectories)")
        traj_cols = [row[1] for row in cursor_traj.fetchall()]
        assert "injected_template_id" in traj_cols
        assert "template_similarity_score" in traj_cols

        cursor_tpl = te._conn.execute("PRAGMA table_info(templates)")
        tpl_cols = [row[1] for row in cursor_tpl.fetchall()]
        assert "originating_trajectory_id" in tpl_cols

    def test_historical_rows_receive_null(self, tmp_path):
        """Historical databases receive NULL for newly added telemetry columns."""
        db_path = tmp_path / "legacy.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, stage TEXT,
                task_description TEXT, artifact_summary TEXT, retry_count INTEGER,
                approved INTEGER, reviewer_feedback TEXT, agent_model TEXT,
                tokens_used INTEGER, latency_ms REAL, recorded_at TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO trajectories VALUES (1, 'p', 'Architect', 't', 's', 0, 1, '', 'm', 10, 1.0, '2026-01-01')"
        )
        conn.commit()
        conn.close()

        from app.memory.learning_loop import LearningLoop
        ll = LearningLoop(db_path=db_path)
        row = ll._conn.execute("SELECT injected_template_id, template_similarity_score FROM trajectories WHERE id=1").fetchone()
        assert row[0] is None
        assert row[1] is None

    def test_injected_template_id_propagated_end_to_end(self, tmp_path):
        """ContextAssembler -> LearningMiddleware -> SQLite stores exact injected_template_id."""
        from app.workflow.context_assembler import ContextAssembler
        from app.memory.learning_loop import Trajectory

        te = _make_template_engine(tmp_path)
        tpl = te.extract_template({"endpoints": "POST /v1"}, stage="BackendDeveloper", project_id="p1")

        assembler = ContextAssembler(template_engine=te)
        result = assembler.assemble("p1", "BackendDeveloper", "task")
        assert result.template_injected is True
        assert result.injected_template_id == tpl.template_id
        assert result.template_similarity_score is None

        ll = _make_learning_loop(tmp_path)
        traj = Trajectory(
            stage="BackendDeveloper", task_description="task", artifact_summary="summary",
            retry_count=0, approved=True, reviewer_feedback="ok", agent_model="model",
            tokens_used=100, latency_ms=10.0, project_id="p1",
            template_injected=result.template_injected,
            injected_template_id=result.injected_template_id,
            template_similarity_score=result.template_similarity_score,
        )
        row_id = ll.record_trajectory(traj)
        assert row_id is not None

        db_row = ll._conn.execute("SELECT injected_template_id, template_similarity_score FROM trajectories WHERE id=?", (row_id,)).fetchone()
        assert db_row[0] == tpl.template_id
        assert db_row[1] is None

    def test_non_injected_stores_null(self, tmp_path):
        """When no template is injected, injected_template_id is NULL."""
        from app.workflow.context_assembler import ContextAssembler

        assembler = ContextAssembler(template_engine=None)
        result = assembler.assemble("p2", "Architect", "task")
        assert result.template_injected is False
        assert result.injected_template_id is None
        assert result.template_similarity_score is None

    def test_template_originating_trajectory_id(self, tmp_path):
        """Approved attempt records trajectory ID on extracted template."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        te = _make_template_engine(tmp_path)
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, template_engine=te, llm_model="m")

        artifact = MagicMock()
        artifact.content = "content"
        artifact.structured_content = {"api": "v1"}
        rr = _make_review_result(approved=True)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            t = MagicMock()
            t.last_call_tokens = 50
            t.last_call_latency = 12.0
            mock_tracker.return_value = t
            mw.on_attempt("BackendDeveloper", "proj-b", "task", 0, artifact, rr)

        mw.on_approval("BackendDeveloper", "proj-b", artifact, 0, rr, [])

        row = te._conn.execute("SELECT template_id, originating_trajectory_id FROM templates WHERE stage='BackendDeveloper'").fetchone()
        assert row is not None
        assert row[1] is not None
        assert int(row[1]) > 0

    def test_interleaved_executions_prevent_cross_talk(self, tmp_path):
        """Interleaved attempts for different projects must not cross-contaminate template attribution."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        te = _make_template_engine(tmp_path)
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, template_engine=te, llm_model="m")

        art_a = MagicMock(content="a", structured_content={"schema": "a"})
        art_b = MagicMock(content="b", structured_content={"schema": "b"})
        rr = _make_review_result(approved=True)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            t = MagicMock(last_call_tokens=50, last_call_latency=10.0)
            mock_tracker.return_value = t

            # Attempt A (Project P1, Architect)
            mw.on_attempt("Architect", "P1", "task A", 0, art_a, rr)

            # Interleaved Attempt B (Project P2, Designer)
            mw.on_attempt("Designer", "P2", "task B", 0, art_b, rr)

        # Approval A (Project P1, Architect)
        mw.on_approval("Architect", "P1", art_a, 0, rr, [])
        # Approval B (Project P2, Designer)
        mw.on_approval("Designer", "P2", art_b, 0, rr, [])

        row_a = te._conn.execute("SELECT originating_trajectory_id FROM templates WHERE stage='Architect' AND source_project_id='P1'").fetchone()
        row_b = te._conn.execute("SELECT originating_trajectory_id FROM templates WHERE stage='Designer' AND source_project_id='P2'").fetchone()

        assert row_a is not None and row_b is not None
        assert int(row_a[0]) < int(row_b[0])  # Architect was attempt 1, Designer was attempt 2

    def test_same_project_different_stages_isolation(self, tmp_path):
        """Different stages for the same project must retain distinct trajectory IDs."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        te = _make_template_engine(tmp_path)
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, template_engine=te, llm_model="m")

        art_arch = MagicMock(content="arch", structured_content={"arch": 1})
        art_qa = MagicMock(content="qa", structured_content={"qa": 1})
        rr = _make_review_result(approved=True)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            mock_tracker.return_value = MagicMock(last_call_tokens=10, last_call_latency=1.0)

            mw.on_attempt("Architect", "P1", "task 1", 0, art_arch, rr)
            mw.on_attempt("QA", "P1", "task 2", 0, art_qa, rr)

        mw.on_approval("Architect", "P1", art_arch, 0, rr, [])
        mw.on_approval("QA", "P1", art_qa, 0, rr, [])

        row_arch = te._conn.execute("SELECT originating_trajectory_id FROM templates WHERE stage='Architect'").fetchone()
        row_qa = te._conn.execute("SELECT originating_trajectory_id FROM templates WHERE stage='QA'").fetchone()

        assert row_arch[0] != row_qa[0]

    def test_failed_trajectory_recording_does_not_reuse_stale_id(self, tmp_path):
        """If on_attempt fails to record a trajectory, a previous trajectory is not stale-assigned."""
        from app.workflow.middleware.learning import LearningMiddleware
        from app.memory.lesson_store import LessonStore

        ll = _make_learning_loop(tmp_path)
        ls = LessonStore(db_path=tmp_path / "lessons.sqlite")
        te = _make_template_engine(tmp_path)
        mw = LearningMiddleware(learning_loop=ll, lesson_store=ls, template_engine=te, llm_model="m")

        art = MagicMock(content="content", structured_content={"v": 1})
        rr = _make_review_result(approved=True)

        with patch("app.llm.cost_tracker.get_shared_cost_tracker") as mock_tracker:
            mock_tracker.return_value = MagicMock(last_call_tokens=10, last_call_latency=1.0)
            mw.on_attempt("Architect", "P1", "task 1", 0, art, rr)

        # Force record_trajectory to return None (simulating failure)
        with patch.object(ll, "record_trajectory", return_value=None):
            mw.on_attempt("Architect", "P1", "task 2", 1, art, rr)

        mw.on_approval("Architect", "P1", art, 1, rr, [])

        row = te._conn.execute("SELECT originating_trajectory_id FROM templates WHERE stage='Architect'").fetchone()
        assert row is not None
        assert row[0] is None  # Must be NULL, not stale '1' from task 1




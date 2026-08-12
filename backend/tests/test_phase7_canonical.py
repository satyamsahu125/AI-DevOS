"""test_phase7_canonical.py — Canonical Phase 7 regression tests.

Covers DEV_PHASES.md §Phase 7 — Template Engine + Model Routing:

  P7-5 / P7-6  ModelRouter: STAGE_PROFILES, env-var per-stage overrides
  P7-3 / P7-4  TemplateEngine: extract_template, find_similar, inject_template
  P7-1 / P7-2  Auto-write paths: approval → LearningLoop, rejection → LessonStore

These tests are independent of FEAT-003 (RAG/secret scrubbing), which is
covered by test_phase7_rag.py.

Running:
    cd backend
    python -m pytest tests/test_phase7_canonical.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# ModelRouter (P7-5, P7-6)
# ---------------------------------------------------------------------------

class TestModelRouterStageProfies:
    """P7-5: STAGE_PROFILES table is populated and returns valid profiles."""

    def _router(self):
        from app.llm.model_router import ModelRouter
        return ModelRouter()

    def test_known_stage_returns_profile(self):
        r = self._router()
        p = r.get_profile("BackendDeveloper")
        assert p is not None
        assert p.temperature == pytest.approx(0.05)

    def test_known_stage_architect_has_max_tokens(self):
        r = self._router()
        p = r.get_profile("Architect")
        assert p.max_tokens == 8192

    def test_known_stage_backend_developer_has_max_tokens(self):
        r = self._router()
        p = r.get_profile("BackendDeveloper")
        assert p.max_tokens == 16384

    def test_known_stage_product_owner_temperature(self):
        r = self._router()
        p = r.get_profile("ProductOwner")
        assert p.temperature == pytest.approx(0.2)

    def test_unknown_stage_returns_default_not_none(self):
        r = self._router()
        p = r.get_profile("NonExistentStage_XYZ")
        assert p is not None
        assert isinstance(p.temperature, float)

    def test_unknown_stage_temperature_is_conservative(self):
        """Unknown stages should be conservative (low temperature)."""
        r = self._router()
        p = r.get_profile("UnknownStage")
        assert p.temperature <= 0.2

    def test_all_canonical_stages_present(self):
        from app.llm.model_router import STAGE_PROFILES
        required = {
            "ProductOwner", "Architect", "BackendDeveloper", "FrontendDeveloper",
            "Designer", "DomainResearch", "BugAnalyst", "Document",
        }
        missing = required - set(STAGE_PROFILES.keys())
        assert not missing, f"STAGE_PROFILES missing stages: {missing}"

    def test_register_profile_overrides_stage(self):
        from app.shared.dto.model_profile import ModelProfile
        r = self._router()
        custom = ModelProfile(provider="ollama", model="llama3", temperature=0.7)
        r.register_profile("TestStage", custom)
        assert r.get_profile("TestStage") is custom


class TestModelRouterEnvVarOverrides:
    """P7-6: STAGE_{STAGE_UPPER}_PROVIDER and STAGE_{STAGE_UPPER}_MODEL override."""

    def _router(self):
        from app.llm.model_router import ModelRouter
        return ModelRouter()

    def test_stage_model_env_var_overrides_model(self, monkeypatch):
        monkeypatch.setenv("STAGE_PRODUCTOWNER_MODEL", "claude-opus-5")
        r = self._router()
        p = r.get_profile("ProductOwner")
        assert p.model == "claude-opus-5"

    def test_stage_provider_env_var_overrides_provider(self, monkeypatch):
        monkeypatch.setenv("STAGE_ARCHITECT_PROVIDER", "gemini")
        r = self._router()
        p = r.get_profile("Architect")
        assert p.provider == "gemini"

    def test_provider_and_model_overridden_independently_provider(self, monkeypatch):
        monkeypatch.setenv("STAGE_BACKENDDEVELOPER_PROVIDER", "ollama")
        monkeypatch.delenv("STAGE_BACKENDDEVELOPER_MODEL", raising=False)
        r = self._router()
        p = r.get_profile("BackendDeveloper")
        assert p.provider == "ollama"
        # model must still be the table default, not empty or wrong
        assert isinstance(p.model, str)

    def test_provider_and_model_overridden_independently_model(self, monkeypatch):
        monkeypatch.delenv("STAGE_BACKENDDEVELOPER_PROVIDER", raising=False)
        monkeypatch.setenv("STAGE_BACKENDDEVELOPER_MODEL", "deepseek-coder")
        r = self._router()
        p = r.get_profile("BackendDeveloper")
        assert p.model == "deepseek-coder"

    def test_temperature_preserved_when_model_overridden(self, monkeypatch):
        monkeypatch.setenv("STAGE_BACKENDDEVELOPER_MODEL", "custom-model")
        r = self._router()
        p = r.get_profile("BackendDeveloper")
        # temperature from STAGE_PROFILES must not be clobbered
        assert p.temperature == pytest.approx(0.05)

    def test_max_tokens_preserved_when_provider_overridden(self, monkeypatch):
        monkeypatch.setenv("STAGE_ARCHITECT_PROVIDER", "gemini")
        r = self._router()
        p = r.get_profile("Architect")
        assert p.max_tokens == 8192

    def test_no_env_var_returns_table_profile_unchanged(self, monkeypatch):
        monkeypatch.delenv("STAGE_PRODUCTOWNER_PROVIDER", raising=False)
        monkeypatch.delenv("STAGE_PRODUCTOWNER_MODEL", raising=False)
        r = self._router()
        from app.llm.model_router import STAGE_PROFILES
        expected = STAGE_PROFILES["ProductOwner"]
        p = r.get_profile("ProductOwner")
        assert p.temperature == expected.temperature
        assert p.max_tokens == expected.max_tokens

    def test_env_var_key_is_stage_name_uppercased(self, monkeypatch):
        """Stage names are uppercased without word-splitting: ProductOwner → PRODUCTOWNER."""
        monkeypatch.setenv("STAGE_PRODUCTOWNER_MODEL", "override-model")
        # A wrongly-keyed variable (e.g. STAGE_PRODUCT_OWNER_MODEL) must NOT apply.
        monkeypatch.delenv("STAGE_PRODUCT_OWNER_MODEL", raising=False)
        r = self._router()
        p = r.get_profile("ProductOwner")
        assert p.model == "override-model"

    def test_env_override_is_read_at_call_time_not_import_time(self, monkeypatch):
        """Setting the env var AFTER constructing ModelRouter must still take effect."""
        r = self._router()
        monkeypatch.setenv("STAGE_REVIEWER_MODEL", "late-model")
        p = r.get_profile("Reviewer")
        assert p.model == "late-model"

    def test_env_override_isolated_to_stage(self, monkeypatch):
        """Override for ProductOwner must not affect BackendDeveloper."""
        monkeypatch.setenv("STAGE_PRODUCTOWNER_MODEL", "special-model")
        r = self._router()
        p_other = r.get_profile("BackendDeveloper")
        assert p_other.model != "special-model"

    def test_both_provider_and_model_overridden(self, monkeypatch):
        monkeypatch.setenv("STAGE_DESIGNER_PROVIDER", "claude")
        monkeypatch.setenv("STAGE_DESIGNER_MODEL", "claude-sonnet-4-6")
        r = self._router()
        p = r.get_profile("Designer")
        assert p.provider == "claude"
        assert p.model == "claude-sonnet-4-6"

    def test_unknown_stage_with_env_override(self, monkeypatch):
        """Env override works even for stages not in STAGE_PROFILES."""
        monkeypatch.setenv("STAGE_MYSTAGE_MODEL", "special")
        r = self._router()
        p = r.get_profile("MyStage")
        assert p.model == "special"


# ---------------------------------------------------------------------------
# TemplateEngine (P7-3)
# ---------------------------------------------------------------------------

class TestTemplateEngineExtract:
    """P7-3: extract_template() derives a structural skeleton from an artifact."""

    def _engine(self, tmp_path):
        from app.learning.template_engine import TemplateEngine
        return TemplateEngine(db_path=tmp_path / "templates.sqlite")

    def test_extract_returns_template(self, tmp_path):
        te = self._engine(tmp_path)
        artifact = {"endpoints": [{"method": "POST", "path": "/users"}], "framework": "FastAPI"}
        tmpl = te.extract_template(artifact, stage="BackendDeveloper", project_id="proj-1")
        assert tmpl is not None
        assert tmpl.stage == "BackendDeveloper"
        assert tmpl.source_project_id == "proj-1"
        assert tmpl.template_id  # non-empty UUID

    def test_extract_replaces_volatile_keys_with_placeholder(self, tmp_path):
        from app.learning.template_engine import _PLACEHOLDER
        te = self._engine(tmp_path)
        artifact = {"project_id": "proj-1", "framework": "FastAPI", "sprint": 2}
        tmpl = te.extract_template(artifact, stage="Architect")
        assert tmpl.structure.get("project_id") == _PLACEHOLDER
        assert tmpl.structure.get("sprint") == _PLACEHOLDER
        # Non-volatile leaf values also become placeholders (structure-only template)
        assert tmpl.structure.get("framework") == _PLACEHOLDER

    def test_extract_preserves_structural_depth(self, tmp_path):
        te = self._engine(tmp_path)
        artifact = {"components": [{"name": "UserService", "methods": ["create", "delete"]}]}
        tmpl = te.extract_template(artifact, stage="Architect")
        assert "components" in tmpl.structure
        assert isinstance(tmpl.structure["components"], list)

    def test_extract_persists_to_sqlite(self, tmp_path):
        import sqlite3
        te = self._engine(tmp_path)
        tmpl = te.extract_template({"key": "val"}, stage="ProductOwner", project_id="p1")
        rows = sqlite3.connect(str(tmp_path / "templates.sqlite")).execute(
            "SELECT stage, source_project_id FROM templates WHERE template_id=?",
            (tmpl.template_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "ProductOwner"
        assert rows[0][1] == "p1"

    def test_extract_non_fatal_on_bad_input(self, tmp_path):
        te = self._engine(tmp_path)
        # Should not raise even with empty artifact
        tmpl = te.extract_template({}, stage="Unknown")
        assert tmpl is not None


class TestTemplateEngineFindSimilar:
    """P7-3: find_similar() returns templates ordered by structural overlap."""

    def _engine(self, tmp_path):
        from app.learning.template_engine import TemplateEngine
        return TemplateEngine(db_path=tmp_path / "templates.sqlite")

    def test_find_similar_returns_empty_when_no_templates(self, tmp_path):
        te = self._engine(tmp_path)
        results = te.find_similar("BackendDeveloper", {"key": "val"})
        assert results == []

    def test_find_similar_returns_templates_for_correct_stage(self, tmp_path):
        te = self._engine(tmp_path)
        te.extract_template({"endpoints": "__PLACEHOLDER__"}, stage="BackendDeveloper")
        te.extract_template({"screens": "__PLACEHOLDER__"}, stage="FrontendDeveloper")
        results = te.find_similar("BackendDeveloper", {"endpoints": "POST /users"})
        stages = {t.stage for t in results}
        assert stages == {"BackendDeveloper"}

    def test_find_similar_respects_limit(self, tmp_path):
        te = self._engine(tmp_path)
        for i in range(10):
            te.extract_template({"k": str(i)}, stage="Architect")
        results = te.find_similar("Architect", {}, limit=3)
        assert len(results) <= 3

    def test_find_similar_latest_template_ranks_first(self, tmp_path):
        te = self._engine(tmp_path)
        # Older template
        te.extract_template(
            {"endpoints": "x", "auth": "x"},
            stage="BackendDeveloper",
        )
        # Newer template
        te.extract_template(
            {"newer_key": "x"},
            stage="BackendDeveloper",
        )
        results = te.find_similar(
            "BackendDeveloper",
            {"endpoints": "POST /v1/users"},
            limit=5,
        )
        assert len(results) == 2
        # Phase A: latest created template must rank first
        assert "newer_key" in results[0].structure

    def test_find_similar_non_fatal_on_empty_context(self, tmp_path):
        te = self._engine(tmp_path)
        te.extract_template({"k": "v"}, stage="Reviewer")
        results = te.find_similar("Reviewer", {})
        assert isinstance(results, list)
        assert len(results) == 1



class TestTemplateEngineInject:
    """P7-3: inject_template() merges template skeleton with concrete context."""

    def _engine(self, tmp_path):
        from app.learning.template_engine import TemplateEngine
        return TemplateEngine(db_path=tmp_path / "templates.sqlite")

    def test_inject_adds_template_keys_missing_from_context(self, tmp_path):
        from app.learning.template_engine import _PLACEHOLDER, Template
        import uuid
        from datetime import datetime, timezone
        te = self._engine(tmp_path)
        template = Template(
            template_id=str(uuid.uuid4()),
            stage="Architect",
            structure={"endpoints": _PLACEHOLDER, "auth": _PLACEHOLDER, "db": _PLACEHOLDER},
            source_project_id="old-proj",
            created_at=datetime.now(timezone.utc),
        )
        context = {"endpoints": "POST /users", "project_id": "new-proj"}
        merged = te.inject_template(template, context)
        assert merged.get("endpoints") == "POST /users"   # context wins
        assert "auth" in merged                           # template key injected
        assert "db" in merged                             # template key injected

    def test_inject_context_values_take_precedence(self, tmp_path):
        from app.learning.template_engine import _PLACEHOLDER, Template
        import uuid
        from datetime import datetime, timezone
        te = self._engine(tmp_path)
        template = Template(
            template_id=str(uuid.uuid4()),
            stage="BackendDeveloper",
            structure={"framework": _PLACEHOLDER},
            source_project_id="p",
            created_at=datetime.now(timezone.utc),
        )
        merged = te.inject_template(template, {"framework": "Django"})
        assert merged["framework"] == "Django"

    def test_inject_non_fatal_on_exception(self, tmp_path):
        from app.learning.template_engine import Template
        import uuid
        from datetime import datetime, timezone
        te = self._engine(tmp_path)
        # Corrupt template structure
        template = Template(
            template_id=str(uuid.uuid4()),
            stage="test",
            structure=None,   # invalid but must not raise
            source_project_id="p",
            created_at=datetime.now(timezone.utc),
        )
        context = {"key": "value"}
        result = te.inject_template(template, context)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Auto-write paths (P7-1, P7-2)
# ---------------------------------------------------------------------------

class TestMemoryOrchestratorAutoWrite:
    """P7-1: record_approval → LearningLoop.record_success()
       P7-2: record_rejection → LessonStore.record()
    """

    def _stage(self, name="BackendDeveloper"):
        from app.shared.enums.stage import Stage
        return Stage(name)

    def _orchestrator(self, learning_loop=None, lesson_store=None):
        from app.memory.orchestrator import MemoryOrchestrator
        return MemoryOrchestrator(
            memory_manager=MagicMock(),
            learning_loop=learning_loop,
            lesson_store=lesson_store,
        )

    def test_approval_calls_record_success(self):
        ll = MagicMock()
        orch = self._orchestrator(learning_loop=ll)
        stage = self._stage("BackendDeveloper")
        orch.record_approval("proj-1", stage, {"result": "done"})
        ll.record_success.assert_called_once()

    def test_approval_passes_correct_stage_name(self):
        ll = MagicMock()
        orch = self._orchestrator(learning_loop=ll)
        stage = self._stage("Architect")
        orch.record_approval("proj-1", stage, {"result": "ok"})
        kwargs = ll.record_success.call_args
        # stage arg is the first positional or keyword "stage"
        call_stage = kwargs[1].get("stage") or kwargs[0][0]
        assert call_stage == "Architect"

    def test_approval_passes_correct_project_id(self):
        ll = MagicMock()
        orch = self._orchestrator(learning_loop=ll)
        stage = self._stage("BackendDeveloper")
        orch.record_approval("my-project", stage, {"x": 1})
        kwargs = ll.record_success.call_args
        call_proj = kwargs[1].get("project_id") or (kwargs[0][9] if len(kwargs[0]) > 9 else None)
        assert call_proj == "my-project"

    def test_rejection_calls_lesson_store_record(self):
        ls = MagicMock()
        orch = self._orchestrator(lesson_store=ls)
        stage = self._stage("BackendDeveloper")
        orch.record_rejection("proj-2", stage, "bad output")
        ls.record.assert_called_once()

    def test_rejection_passes_correct_stage_and_project(self):
        ls = MagicMock()
        orch = self._orchestrator(lesson_store=ls)
        stage = self._stage("QA")
        orch.record_rejection("proj-qa", stage, "failed tests")
        kwargs = ls.record.call_args
        call_stage = kwargs[1].get("stage") or kwargs[0][0]
        call_proj  = kwargs[1].get("project_id") or kwargs[0][1]
        assert call_stage == "QA"
        assert call_proj == "proj-qa"

    def test_rejection_includes_feedback_in_what_failed(self):
        ls = MagicMock()
        orch = self._orchestrator(lesson_store=ls)
        stage = self._stage("Reviewer")
        orch.record_rejection("proj-3", stage, "missing unit tests")
        kwargs = ls.record.call_args
        what_failed = kwargs[1].get("what_failed", "")
        assert "missing unit tests" in what_failed

    def test_approval_without_learning_loop_does_not_crash(self):
        """LearningLoop is optional — None must not raise."""
        orch = self._orchestrator(learning_loop=None)
        stage = self._stage("ProductOwner")
        orch.record_approval("proj-x", stage, {})  # must not raise

    def test_rejection_without_lesson_store_does_not_crash(self):
        """LessonStore is optional — None must not raise."""
        orch = self._orchestrator(lesson_store=None)
        stage = self._stage("BugAnalyst")
        orch.record_rejection("proj-y", stage, "no tests")  # must not raise

    def test_approval_learning_loop_failure_is_non_fatal(self):
        """If LearningLoop.record_success() raises, record_approval must not propagate."""
        ll = MagicMock()
        ll.record_success.side_effect = RuntimeError("DB down")
        orch = self._orchestrator(learning_loop=ll)
        stage = self._stage("BackendDeveloper")
        orch.record_approval("proj-z", stage, {"result": "ok"})  # must not raise

    def test_rejection_lesson_store_failure_is_non_fatal(self):
        """If LessonStore.record() raises, record_rejection must not propagate."""
        ls = MagicMock()
        ls.record.side_effect = RuntimeError("DB locked")
        orch = self._orchestrator(lesson_store=ls)
        stage = self._stage("QA")
        orch.record_rejection("proj-z2", stage, "timeout")  # must not raise

"""test_phase9_context_manager.py — P9-2c focused regression tests.

Verifies:
  1. ContextManager constructs with mocked dependencies (no external libs required).
  2. build_context() returns AgentContext with expected fields populated.
  3. MemoryOrchestrator._load_semantic() calls context_manager.build_context().
  4. _load_semantic() returns lessons and patterns from context_manager.
  5. _load_semantic() with no context_manager returns ([], []).
  6. get_context() emits a structured "context_assembly" log entry (INFO level).
  7. Structured log contains layer_2_episodic with expected keys.
  8. Structured log contains layer_3_semantic with expected keys.
  9. ContextAssembler delegates to MemoryOrchestrator when it is wired.
  10. ContextAssembler + MemoryOrchestrator degrades gracefully when
      context_manager is None (semantic layer returns empty, rest unchanged).

Running:
    cd backend
    python -m pytest tests/test_phase9_context_manager.py -v
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_learning_loop(patterns: list[str] | None = None) -> MagicMock:
    """Return a mocked LearningLoop whose get_agent_performance() returns a real dataclass."""
    from app.memory.learning_loop import AgentPerformance

    ll = MagicMock()
    ll.get_relevant_patterns.return_value = patterns if patterns is not None else []
    ll.get_agent_performance.return_value = AgentPerformance(
        total=5, success_rate=0.8, avg_retries=1.2, avg_tokens=1800.0, avg_latency=4.1,
    )
    return ll


def _make_context_manager(
    lessons: list[str] | None = None,
    past_patterns: list[str] | None = None,
) -> object:
    """Build a real ContextManager with mocked dependencies."""
    from app.context.context import ContextManager

    mm = MagicMock()
    mm.load.return_value = None
    wm = MagicMock()
    wm.load_project_json.return_value = {"name": "test-project"}
    ll = _make_learning_loop(patterns=past_patterns or [])
    ls = MagicMock()
    # get_lessons() returns Lesson-like objects with what_worked and what_failed attributes.
    lesson_objs = []
    for txt in (lessons or []):
        obj = MagicMock()
        obj.what_worked = txt
        obj.what_failed = ""
        lesson_objs.append(obj)
    ls.get_lessons.return_value = lesson_objs

    return ContextManager(
        memory_manager=mm,
        learning_loop=ll,
        lesson_store=ls,
        workspace_manager=wm,
        prompt_analyzer=None,  # prompt_analyzer=None → creates PromptQualityAnalyzer with no knowledge → []
    )


def _make_memory_orchestrator(context_manager=None) -> object:
    """Build a MemoryOrchestrator with minimal mocked dependencies."""
    from app.memory.orchestrator import MemoryOrchestrator

    mm = MagicMock()
    mm.load_stage_output.return_value = None
    mm.load_sprint_stage_output.return_value = None
    am = MagicMock()
    am.get_artifact.return_value = None
    wm = MagicMock()
    wm.load_project_json.return_value = {"name": "test-proj"}

    return MemoryOrchestrator(
        memory_manager=mm,
        artifact_manager=am,
        workspace_manager=wm,
        context_manager=context_manager,
        context_orchestrator=None,
    )


# ---------------------------------------------------------------------------
# 1. ContextManager construction
# ---------------------------------------------------------------------------


class TestContextManagerConstruction:
    """ContextManager can be instantiated with mocked deps (no external libraries needed)."""

    def test_constructs_with_mocked_deps(self):
        """ContextManager.__init__() must not raise when all deps are mocked."""
        cm = _make_context_manager()
        assert cm is not None

    def test_build_context_returns_agent_context(self):
        """build_context() must return an AgentContext with known fields."""
        from app.context.context import AgentContext

        cm = _make_context_manager(lessons=["Worked: used auth middleware"])
        result = cm.build_context("proj-1", "BackendDeveloper", "build auth module")

        assert isinstance(result, AgentContext), "Expected AgentContext, got %s" % type(result)
        assert result.agent_name == "BackendDeveloper"
        assert result.project_name == "test-project"
        assert isinstance(result.lessons, list)
        assert isinstance(result.past_patterns, list)
        assert isinstance(result.cross_project_patterns, list)


# ---------------------------------------------------------------------------
# 2. Semantic layer wiring (_load_semantic)
# ---------------------------------------------------------------------------


class TestSemanticLayerWiring:
    """MemoryOrchestrator._load_semantic() correctly delegates to ContextManager."""

    def test_load_semantic_calls_build_context(self):
        """_load_semantic() must call context_manager.build_context() exactly once."""
        from app.memory.orchestrator import MemoryOrchestrator
        from app.shared.enums.stage import Stage

        mock_cm = MagicMock()
        # build_context must return an object whose .lessons / .past_patterns / .cross_project_patterns work
        fake_ctx = MagicMock()
        fake_ctx.lessons = ["lesson-A"]
        fake_ctx.past_patterns = ["pattern-B"]
        fake_ctx.cross_project_patterns = []
        mock_cm.build_context.return_value = fake_ctx

        mo = _make_memory_orchestrator(context_manager=mock_cm)
        mo._load_semantic("proj-x", Stage("BackendDeveloper"))

        mock_cm.build_context.assert_called_once_with("proj-x", "BackendDeveloper")

    def test_load_semantic_returns_lessons_and_patterns(self):
        """_load_semantic() must surface lessons and patterns from context_manager."""
        from app.memory.orchestrator import MemoryOrchestrator
        from app.shared.enums.stage import Stage

        mock_cm = MagicMock()
        fake_ctx = MagicMock()
        fake_ctx.lessons = ["Worked: explicit schema validation"]
        fake_ctx.past_patterns = ["pattern-from-loop"]
        fake_ctx.cross_project_patterns = ["cross-project-hit"]
        mock_cm.build_context.return_value = fake_ctx

        mo = _make_memory_orchestrator(context_manager=mock_cm)
        lessons, patterns = mo._load_semantic("proj-x", Stage("Architect"))

        assert "Worked: explicit schema validation" in lessons
        assert "pattern-from-loop" in patterns
        assert "cross-project-hit" in patterns

    def test_load_semantic_with_none_context_manager_returns_empty(self):
        """When context_manager is None, _load_semantic() must return ([], [])."""
        from app.shared.enums.stage import Stage

        mo = _make_memory_orchestrator(context_manager=None)
        lessons, patterns = mo._load_semantic("proj-y", Stage("QA"))

        assert lessons == []
        assert patterns == []


# ---------------------------------------------------------------------------
# 3. Structured layer-contribution logging
# ---------------------------------------------------------------------------


class TestLayerContributionLogging:
    """get_context() emits a structured JSON log at INFO level after assembly."""

    def _get_assembly_log(self, caplog, project_id: str, stage_name: str) -> dict | None:
        """Run get_context() and return the parsed 'context_assembly' log entry, or None."""
        from app.shared.enums.stage import Stage

        cm = _make_context_manager(lessons=["a lesson"], past_patterns=["p1"])
        mo = _make_memory_orchestrator(context_manager=cm)

        with caplog.at_level(logging.INFO, logger="app.memory.orchestrator"):
            mo.get_context(project_id, Stage(stage_name))

        for record in caplog.records:
            if record.name == "app.memory.orchestrator" and "context_assembly" in record.getMessage():
                # The log message is 'context_assembly: {json...}'
                _, _, json_part = record.getMessage().partition(": ")
                try:
                    return json.loads(json_part)
                except json.JSONDecodeError:
                    return None
        return None

    def test_get_context_emits_structured_log(self, caplog):
        """get_context() must emit an INFO log containing 'event': 'context_assembly'."""
        entry = self._get_assembly_log(caplog, "proj-1", "Architect")
        assert entry is not None, "No context_assembly log entry found"
        assert entry["event"] == "context_assembly"
        assert entry["project"] == "proj-1"
        assert entry["stage"] == "Architect"

    def test_layer_log_contains_layer_2_episodic_keys(self, caplog):
        """Structured log must contain layer_2_episodic with required keys."""
        entry = self._get_assembly_log(caplog, "proj-2", "BackendDeveloper")
        assert entry is not None, "No context_assembly log entry found"
        layer2 = entry.get("layer_2_episodic")
        assert layer2 is not None, "layer_2_episodic missing from log"
        assert "predecessor_count" in layer2
        assert "has_clarification" in layer2
        assert "has_architecture" in layer2
        assert "has_design" in layer2

    def test_layer_log_contains_layer_3_semantic_keys(self, caplog):
        """Structured log must contain layer_3_semantic with lessons_count and patterns_count."""
        entry = self._get_assembly_log(caplog, "proj-3", "QA")
        assert entry is not None, "No context_assembly log entry found"
        layer3 = entry.get("layer_3_semantic")
        assert layer3 is not None, "layer_3_semantic missing from log"
        assert "lessons_count" in layer3
        assert "patterns_count" in layer3
        assert "context_manager_active" in layer3
        assert layer3["context_manager_active"] is True

    def test_layer_log_layer_3_semantic_counts_accurate(self, caplog):
        """lessons_count and patterns_count must reflect actual semantic layer content."""
        from app.shared.enums.stage import Stage

        # 2 lessons, 3 patterns (1 past_pattern + 0 cross_project because no knowledge_memory)
        cm = _make_context_manager(
            lessons=["lesson-one", "lesson-two"],
            past_patterns=["pat-A", "pat-B", "pat-C"],
        )
        mo = _make_memory_orchestrator(context_manager=cm)

        with caplog.at_level(logging.INFO, logger="app.memory.orchestrator"):
            mo.get_context("proj-4", Stage("Architect"))

        entry = None
        for record in caplog.records:
            if record.name == "app.memory.orchestrator" and "context_assembly" in record.getMessage():
                _, _, json_part = record.getMessage().partition(": ")
                try:
                    entry = json.loads(json_part)
                except json.JSONDecodeError:
                    pass
                break

        assert entry is not None
        layer3 = entry["layer_3_semantic"]
        # 2 lessons (lesson_summaries) + 3 patterns (past_patterns, no cross_project)
        assert layer3["lessons_count"] == 2
        assert layer3["patterns_count"] == 3


# ---------------------------------------------------------------------------
# 4. ContextAssembler wiring
# ---------------------------------------------------------------------------


class TestContextAssemblerWiring:
    """ContextAssembler correctly delegates to MemoryOrchestrator and degrades gracefully."""

    def test_assembler_uses_orchestrator_path_when_available(self):
        """ContextAssembler must call memory_orchestrator.get_context() when it is wired."""
        from app.workflow.context_assembler import ContextAssembler
        from app.shared.enums.stage import Stage

        mock_mo = MagicMock()
        # get_context() returns a StageContext-like object with to_prompt_dict()
        fake_stage_ctx = MagicMock()
        fake_stage_ctx.to_prompt_dict.return_value = {"original_request": "build an app"}
        mock_mo.get_context.return_value = fake_stage_ctx

        assembler = ContextAssembler(memory_orchestrator=mock_mo)
        result = assembler.assemble("proj-1", "Architect", "build an app")

        mock_mo.get_context.assert_called_once_with("proj-1", Stage("Architect"))
        # assemble() returns AssembleResult; .context carries the string payload.
        from app.workflow.context_assembler import AssembleResult
        assert isinstance(result, AssembleResult)
        assert isinstance(result.context, str)

    def test_assembler_degrades_gracefully_when_context_manager_none(self):
        """ContextAssembler + MemoryOrchestrator with context_manager=None must still return a str."""
        from app.workflow.context_assembler import ContextAssembler

        mo = _make_memory_orchestrator(context_manager=None)
        assembler = ContextAssembler(
            memory_orchestrator=mo,
            memory_manager=None,
        )
        result = assembler.assemble("proj-z", "Architect", "build a service")

        from app.workflow.context_assembler import AssembleResult
        assert isinstance(result, AssembleResult)
        assert isinstance(result.context, str)
        assert len(result.context) > 0

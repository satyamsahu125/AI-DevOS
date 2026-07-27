"""Tests for Phase 2 agents: TechLeadAgent and BugAnalystAgent.

Design constraints (same as test_agents_complete.py):
  - No live LLM calls — _StubLLM echoes a canned JSON reply.
  - No real filesystem writes — workspace_manager injected via tmp_path.
  - Each agent and its action are tested independently.
  - Factory can instantiate both agents by name.

Test coverage
-------------
TechLeadAgent:
  - Instantiates without workspace_manager or llm_manager.
  - artifact_name is "tech_review".
  - approved=True path: LLM returns {"approved": true, "violations": []}.
  - approved=False path: LLM returns {"approved": false, "violations": [...]}.
  - review() convenience method returns structured dict.
  - ArtifactStore write called when workspace_manager is wired.

BugAnalystAgent:
  - Instantiates without workspace_manager or llm_manager.
  - artifact_name is "bug_analysis".
  - code_bug classification: LLM classifies as code_bug.
  - spec_bug classification: LLM classifies as spec_bug.
  - analyse() convenience method assembles context and returns structured dict.
  - ArtifactStore write called when workspace_manager is wired.

Factory:
  - AgentFactory can create "tech_lead" and "bug_analyst" by name.

Stage enum:
  - Stage.TechLead and Stage.BugAnalyst exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Patch safety_policy before any app import (it tries to open a DB on mount).
sys.modules.setdefault("app.execution.safety_policy", MagicMock())

from app.llm.response import LLMResponse


# ===========================================================================
# Shared stubs
# ===========================================================================

class _StubLLM:
    """Returns a canned JSON reply — no live Ollama needed."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[str] = []

    def generate_text(self, prompt: str, system_prompt: str = "", **kwargs) -> LLMResponse:
        self.calls.append(prompt)
        return LLMResponse(
            content=self._reply,
            model="stub",
            finish_reason="stop",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )


def _llm(reply_dict: dict) -> _StubLLM:
    return _StubLLM(json.dumps(reply_dict))


def _ctx(content: str = "review context", project_id: str = "proj-test", sprint: int = 1, iteration: int = 1):
    return SimpleNamespace(
        content=content,
        project_id=project_id,
        sprint_number=sprint,
        iteration=iteration,
    )


# ===========================================================================
# TechLeadAgent
# ===========================================================================

class TestTechLeadAgent:

    def _make(self, reply_dict: dict, workspace_manager=None):
        from app.agents.tech_lead import TechLeadAgent
        return TechLeadAgent(
            llm_manager=_llm(reply_dict),
            workspace_manager=workspace_manager,
        )

    def test_instantiates_without_injections(self) -> None:
        from app.agents.tech_lead import TechLeadAgent
        agent = TechLeadAgent()
        assert agent is not None

    def test_artifact_name(self) -> None:
        from app.agents.tech_lead import TechLeadAgent
        assert TechLeadAgent.artifact_name == "tech_review"

    def test_approved_true_path(self) -> None:
        """LLM returns approved=true → artifact structured_content reflects it."""
        reply = {"approved": True, "violations": [], "summary": "All good.", "iteration": 1}
        agent = self._make(reply)
        artifact = agent.execute(_ctx())
        assert artifact.structured_content.get("approved") is True
        assert artifact.structured_content.get("violations") == []

    def test_approved_false_with_violations(self) -> None:
        """LLM returns approved=false with violations → artifact carries them."""
        reply = {
            "approved": False,
            "violations": [
                {"severity": "critical", "file": "backend/main.py", "rule": "no-auth", "detail": "Missing JWT"}
            ],
            "summary": "Critical auth violation.",
            "iteration": 1,
        }
        agent = self._make(reply)
        artifact = agent.execute(_ctx())
        assert artifact.structured_content.get("approved") is False
        violations = artifact.structured_content.get("violations", [])
        assert len(violations) == 1
        assert violations[0]["severity"] == "critical"

    def test_approved_default_false_on_empty_json(self) -> None:
        """When LLM returns empty JSON, approved defaults to False (safe)."""
        agent = self._make({})
        artifact = agent.execute(_ctx())
        assert artifact.structured_content.get("approved") is False

    def test_iteration_stamped_in_output(self) -> None:
        """iteration from context is stamped onto output when LLM omits it."""
        agent = self._make({"approved": True, "violations": []})
        ctx = _ctx(iteration=3)
        artifact = agent.execute(ctx)
        assert artifact.structured_content.get("iteration") == 3

    def test_review_convenience_method(self) -> None:
        """review() wraps execute() and returns a plain dict."""
        reply = {"approved": True, "violations": [], "iteration": 2}
        agent = self._make(reply)
        result = agent.review("proj-x", sprint_number=2, context_text="code review ctx", iteration=2)
        assert isinstance(result, dict)
        assert result.get("approved") is True

    def test_artifact_store_written_when_workspace_manager_wired(self, tmp_path: Path) -> None:
        """review() writes to ArtifactStore when workspace_manager is provided."""
        from app.workspace.manager import WorkspaceManager
        wm = WorkspaceManager(root=tmp_path)
        reply = {"approved": True, "violations": []}
        agent = self._make(reply, workspace_manager=wm)
        agent.review("proj-ws", sprint_number=1, context_text="code review ctx")
        store = wm.get_artifact_store("proj-ws")
        assert store.exists("sprint_1", "tech_review")

    def test_no_error_without_workspace_manager(self) -> None:
        """When workspace_manager is None, execute() does NOT raise."""
        agent = self._make({"approved": True, "violations": []})
        artifact = agent.execute(_ctx())
        assert artifact is not None


# ===========================================================================
# BugAnalystAgent
# ===========================================================================

class TestBugAnalystAgent:

    def _make(self, reply_dict: dict, workspace_manager=None):
        from app.agents.bug_analyst import BugAnalystAgent
        return BugAnalystAgent(
            llm_manager=_llm(reply_dict),
            workspace_manager=workspace_manager,
        )

    def test_instantiates_without_injections(self) -> None:
        from app.agents.bug_analyst import BugAnalystAgent
        agent = BugAnalystAgent()
        assert agent is not None

    def test_artifact_name(self) -> None:
        from app.agents.bug_analyst import BugAnalystAgent
        assert BugAnalystAgent.artifact_name == "bug_analysis"

    def test_code_bug_classification(self) -> None:
        """LLM classifies as code_bug → structured output carries correct type."""
        reply = {
            "type": "code_bug",
            "root_artifact": "backend code",
            "affected_agent": "Backend",
            "fix_instruction": "Fix null-pointer in auth.py line 42.",
            "failures_analysed": 1,
            "sprint": 1,
            "iteration": 1,
        }
        agent = self._make(reply)
        artifact = agent.execute(_ctx())
        assert artifact.structured_content.get("type") == "code_bug"
        assert artifact.structured_content.get("affected_agent") == "Backend"
        assert "fix_instruction" in artifact.structured_content

    def test_spec_bug_classification(self) -> None:
        """LLM classifies as spec_bug → affected_agent is ProductOwner."""
        reply = {
            "type": "spec_bug",
            "root_artifact": "user_stories",
            "affected_agent": "ProductOwner",
            "fix_instruction": "US-03 is missing the cancellation acceptance criterion.",
            "failures_analysed": 2,
            "sprint": 2,
            "iteration": 1,
        }
        agent = self._make(reply)
        artifact = agent.execute(_ctx(sprint=2))
        assert artifact.structured_content.get("type") == "spec_bug"
        assert artifact.structured_content.get("affected_agent") == "ProductOwner"
        assert artifact.structured_content.get("root_artifact") == "user_stories"

    def test_architecture_bug_classification(self) -> None:
        reply = {
            "type": "architecture_bug",
            "root_artifact": "architecture",
            "affected_agent": "Architect",
            "fix_instruction": "DB layer is bypassed. Add repository pattern.",
            "failures_analysed": 1,
            "sprint": 1,
            "iteration": 2,
        }
        agent = self._make(reply)
        artifact = agent.execute(_ctx())
        assert artifact.structured_content.get("type") == "architecture_bug"
        assert artifact.structured_content.get("affected_agent") == "Architect"

    def test_security_violation_classification(self) -> None:
        reply = {
            "type": "security_violation",
            "root_artifact": "security_rules",
            "affected_agent": "Backend",
            "fix_instruction": "Remove hardcoded API key from config.py.",
            "failures_analysed": 1,
            "sprint": 3,
            "iteration": 1,
        }
        agent = self._make(reply)
        artifact = agent.execute(_ctx(sprint=3))
        assert artifact.structured_content.get("type") == "security_violation"

    def test_defaults_applied_on_empty_json(self) -> None:
        """If LLM returns empty JSON, safe defaults are applied."""
        agent = self._make({})
        artifact = agent.execute(_ctx())
        sc = artifact.structured_content
        assert sc.get("type") == "code_bug"
        assert sc.get("affected_agent") == "Backend"
        assert "fix_instruction" in sc

    def test_analyse_convenience_method(self) -> None:
        """analyse() assembles context parts and returns a plain dict."""
        reply = {
            "type": "spec_bug",
            "root_artifact": "user_stories",
            "affected_agent": "ProductOwner",
            "fix_instruction": "Add missing story.",
            "sprint": 1,
            "iteration": 1,
        }
        agent = self._make(reply)
        result = agent.analyse(
            project_id="proj-y",
            sprint_number=1,
            qa_findings="Test_login_fails: expected 200 got 401",
            user_stories="As a user I want to log in",
            architecture="REST API with JWT",
        )
        assert isinstance(result, dict)
        assert result.get("type") == "spec_bug"

    def test_artifact_store_written_when_workspace_manager_wired(self, tmp_path: Path) -> None:
        """analyse() writes to ArtifactStore when workspace_manager is provided."""
        from app.workspace.manager import WorkspaceManager
        wm = WorkspaceManager(root=tmp_path)
        reply = {"type": "code_bug", "affected_agent": "Backend", "fix_instruction": "Fix it."}
        agent = self._make(reply, workspace_manager=wm)
        agent.analyse("proj-ba", sprint_number=2, qa_findings="test_login_fails")
        store = wm.get_artifact_store("proj-ba")
        assert store.exists("sprint_2", "bug_analysis")

    def test_no_error_without_workspace_manager(self) -> None:
        agent = self._make({"type": "code_bug"})
        artifact = agent.execute(_ctx())
        assert artifact is not None


# ===========================================================================
# Factory registration
# ===========================================================================

class TestFactoryRegistration:

    def test_factory_creates_tech_lead(self) -> None:
        from app.agents.factory import AgentFactory
        from app.agents.tech_lead import TechLeadAgent
        factory = AgentFactory()
        agent = factory.create("tech_lead")
        assert isinstance(agent, TechLeadAgent)

    def test_factory_creates_bug_analyst(self) -> None:
        from app.agents.factory import AgentFactory
        from app.agents.bug_analyst import BugAnalystAgent
        factory = AgentFactory()
        agent = factory.create("bug_analyst")
        assert isinstance(agent, BugAnalystAgent)


# ===========================================================================
# Stage enum
# ===========================================================================

class TestStageEnum:

    def test_tech_lead_stage_exists(self) -> None:
        from app.shared.enums.stage import Stage
        assert Stage.TechLead == "TechLead"

    def test_bug_analyst_stage_exists(self) -> None:
        from app.shared.enums.stage import Stage
        assert Stage.BugAnalyst == "BugAnalyst"

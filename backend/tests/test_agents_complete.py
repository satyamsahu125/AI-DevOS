"""Comprehensive test suite for all AI DevOS development agents.

Covers every agent in app/agents/:
  - StrategicReviewAgent, ProductOwnerAgent, ArchitectAgent, DesignerAgent
  - SecurityAgent, SprintPlannerAgent, ScrumMasterAgent, RetroAgent
  - ClarificationAgent, DomainResearcherAgent
  - FilePlannerAgent (alias FileStructurePlannerAgent)
  - QAAgent, DevOpsAgent, DocumentAgent
  - BackendDeveloperAgent, FrontendDeveloperAgent
  - AgentFactory, AgentRegistry, AgentResolver

Design constraints:
  - No live LLM calls — StubLLMManager echoes the prompt
  - No real filesystem writes — ProjectWriter patched / MagicMock
  - Each agent class and its primary_action are tested independently
  - Factory creates every registered agent without error
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Patch safety_policy before any app import (it tries to open DB on Windows mount)
sys.modules.setdefault("app.execution.safety_policy", MagicMock())

from app.llm.response import LLMResponse
from app.shared.models.stage_artifact import StageArtifact


# ---------------------------------------------------------------------------
# Shared stub LLM
# ---------------------------------------------------------------------------

class _StubLLM:
    """Echoes the prompt back as the response content — no live Ollama needed."""

    def __init__(self, reply: str | None = None) -> None:
        self._reply = reply
        self.calls: list[str] = []

    def generate_text(self, prompt: str, system_prompt: str = "", **kwargs) -> LLMResponse:
        self.calls.append(prompt)
        content = self._reply if self._reply is not None else prompt
        return LLMResponse(
            content=content, model="stub", finish_reason="stop",
            input_tokens=0, output_tokens=0, total_tokens=0,
        )


def _stub(reply: str | None = None) -> _StubLLM:
    return _StubLLM(reply=reply)


def _ctx(content: str = "Build a todo app") -> SimpleNamespace:
    return SimpleNamespace(content=content)


# ---------------------------------------------------------------------------
# Helper: assert StageArtifact shape
# ---------------------------------------------------------------------------

def _assert_artifact(tc: unittest.TestCase, artifact: object, expected_name: str | None = None) -> None:
    tc.assertIsInstance(artifact, StageArtifact)
    tc.assertIsNotNone(artifact.content)
    if expected_name is not None:
        tc.assertEqual(artifact.name, expected_name)


# ===========================================================================
# Simple pipeline agents (prompt_builder pattern)
# ===========================================================================

class TestStrategicReviewAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.strategic_review import StrategicReviewAgent
        return StrategicReviewAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.strategic_review import StrategicReviewAgent
        from app.actions.write_strategic_brief import WriteStrategicBriefAction
        agent = StrategicReviewAgent()
        self.assertIsNotNone(agent)
        self.assertIsInstance(agent.primary_action, WriteStrategicBriefAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "strategic-review-output")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "strategic-review-output")

    def test_execute_passes_content_to_llm(self):
        llm = _stub()
        self._make(llm).execute(_ctx("Build a food delivery app"))
        self.assertTrue(any("food delivery" in c for c in llm.calls))


class TestProductOwnerAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.product_owner import ProductOwnerAgent
        return ProductOwnerAgent(llm_manager=llm or _stub())

    _REQ_JSON = '{"project_name": "x", "goals": [], "user_stories": [], "acceptance_criteria": [], "constraints": [], "out_of_scope": []}'

    def test_instantiates_without_llm(self):
        from app.agents.product_owner import ProductOwnerAgent
        from app.actions.write_requirements import WriteRequirementsAction
        agent = ProductOwnerAgent()
        self.assertIsInstance(agent.primary_action, WriteRequirementsAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "product-owner-output")

    def test_execute_returns_artifact(self):
        llm = _stub(self._REQ_JSON)
        artifact = self._make(llm).execute(_ctx())
        _assert_artifact(self, artifact, "product-owner-output")

    def test_execute_passes_content_to_llm(self):
        llm = _stub(self._REQ_JSON)
        self._make(llm).execute(_ctx("Invoicing tool for freelancers"))
        self.assertTrue(any("freelancers" in c for c in llm.calls))


class TestArchitectAgent(unittest.TestCase):
    # WriteArchitectureAction._parse_structured raises SchemaValidationError on empty JSON,
    # so we inject a mock primary_action to test execute() without schema validation.
    _ARCH_JSON = (
        '{"implementation_approach":"layered","approach":"REST","layers":["api","service","db"],'
        '"modules":[{"name":"auth","purpose":"auth"}],"api_endpoints":[],"api_design":[],"data_models":[],'
        '"tech_stack":{"backend":"FastAPI"},"deployment_notes":"","scalability_notes":"",'
        '"out_of_scope":[],"anything_unclear":""}'
    )

    def _make(self, llm=None):
        from app.agents.architect import ArchitectAgent
        return ArchitectAgent(llm_manager=llm or _stub(self._ARCH_JSON))

    def _make_mocked(self):
        """Return an ArchitectAgent whose primary_action is a mock (bypasses schema validation)."""
        from app.agents.architect import ArchitectAgent
        from app.actions.base_action import ActionOutput
        mock_action = MagicMock()
        mock_action.name = "WriteArchitecture"
        mock_action.run.return_value = ActionOutput(content="architecture output", structured={})
        return ArchitectAgent(llm_manager=_stub(), primary_action=mock_action), mock_action

    def test_instantiates_without_llm(self):
        from app.agents.architect import ArchitectAgent
        from app.actions.write_architecture import WriteArchitectureAction
        agent = ArchitectAgent()
        self.assertIsInstance(agent.primary_action, WriteArchitectureAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "architecture")

    def test_execute_returns_artifact(self):
        agent, mock_action = self._make_mocked()
        artifact = agent.execute(_ctx())
        _assert_artifact(self, artifact, "architecture")
        mock_action.run.assert_called_once()

    def test_execute_includes_content_in_prompt(self):
        """Verify the context is forwarded to primary_action.run."""
        agent, mock_action = self._make_mocked()
        ctx = _ctx("Microservice with gRPC")
        agent.execute(ctx)
        call_args = mock_action.run.call_args
        self.assertIs(call_args[0][0], ctx)  # first positional arg is context

    def test_execute_with_valid_json_llm_passes_schema(self):
        """When LLM returns valid architecture JSON, no SchemaValidationError is raised."""
        artifact = self._make(_stub(self._ARCH_JSON)).execute(_ctx())
        _assert_artifact(self, artifact, "architecture")


class TestDesignerAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.designer import DesignerAgent
        return DesignerAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.designer import DesignerAgent
        from app.actions.write_design import WriteDesignAction
        agent = DesignerAgent()
        self.assertIsInstance(agent.primary_action, WriteDesignAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "designer-output")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "designer-output")


class TestSecurityAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.security import SecurityAgent
        return SecurityAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.security import SecurityAgent
        from app.actions.write_security_report import WriteSecurityReportAction
        agent = SecurityAgent()
        self.assertIsInstance(agent.primary_action, WriteSecurityReportAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "security-output")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "security-output")


class TestSprintPlannerAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.sprint_planner import SprintPlannerAgent
        return SprintPlannerAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.sprint_planner import SprintPlannerAgent
        from app.actions.plan_sprints import PlanSprintsAction
        agent = SprintPlannerAgent()
        self.assertIsInstance(agent.primary_action, PlanSprintsAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "sprint-plan")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "sprint-plan")


class TestScrumMasterAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.scrum_master import ScrumMasterAgent
        return ScrumMasterAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.scrum_master import ScrumMasterAgent
        from app.actions.write_scrum_plan import WriteScrumPlanAction
        agent = ScrumMasterAgent()
        self.assertIsInstance(agent.primary_action, WriteScrumPlanAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "scrum_master")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "scrum_master")


class TestRetroAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.retro import RetroAgent
        return RetroAgent(llm_manager=llm or _stub())

    def test_instantiates_without_llm(self):
        from app.agents.retro import RetroAgent
        from app.actions.write_retrospective import WriteRetrospectiveAction
        agent = RetroAgent()
        self.assertIsInstance(agent.primary_action, WriteRetrospectiveAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "retro-output")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "retro-output")

    def test_execute_includes_content_in_prompt(self):
        llm = _stub()
        self._make(llm).execute(_ctx("Sprint 3 retrospective input"))
        self.assertTrue(any("Sprint 3" in c for c in llm.calls))


# ===========================================================================
# ClarificationAgent
# ===========================================================================

class TestClarificationAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.clarification import ClarificationAgent
        return ClarificationAgent(llm_manager=llm or _stub('{"questions": []}'))

    def test_instantiates_without_llm(self):
        from app.agents.clarification import ClarificationAgent
        from app.actions.clarify_requirements import ClarifyRequirementsAction
        agent = ClarificationAgent()
        self.assertIsInstance(agent.primary_action, ClarifyRequirementsAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "clarification-report")

    def test_has_generate_and_process_sub_actions(self):
        from app.actions.clarify_requirements import GenerateQuestionsAction, ProcessAnswersAction
        agent = self._make()
        self.assertIsInstance(agent.generate_action, GenerateQuestionsAction)
        self.assertIsInstance(agent.process_action, ProcessAnswersAction)

    def test_generate_questions_calls_llm(self):
        llm = _stub('{"questions": []}')
        agent = self._make(llm)
        result = agent.generate_questions("Build a food delivery app")
        self.assertGreater(len(llm.calls), 0)
        self.assertTrue(any("food delivery" in c for c in llm.calls))

    def test_generate_questions_with_domain_brief(self):
        """Domain brief is injected into the generate_questions prompt."""
        llm = _stub('{"questions": []}')
        agent = self._make(llm)
        brief = {"domain": "e-commerce", "complexity": "high"}
        agent.generate_questions("Build a shop", domain_brief=brief)
        self.assertGreater(len(llm.calls), 0)

    def test_process_answers_calls_llm(self):
        llm = _stub('{"summary": "User wants a todo app", "requirements": []}')
        agent = self._make(llm)
        qa = {"q1": {"question": "Who is the target user?", "answer": "Developers"}}
        result = agent.process_answers("Build a todo app", qa)
        self.assertGreater(len(llm.calls), 0)

    def test_execute_returns_stage_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "clarification-report")


# ===========================================================================
# DomainResearcherAgent
# ===========================================================================

class TestDomainResearcherAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.domain_researcher import DomainResearcherAgent
        return DomainResearcherAgent(llm_manager=llm or _stub("{}"))

    def test_instantiates_without_llm(self):
        from app.agents.domain_researcher import DomainResearcherAgent
        agent = DomainResearcherAgent()
        self.assertIsNotNone(agent)

    def test_default_action_is_concrete(self):
        """_build_default_action must return a callable concrete object, not abstract BaseAction."""
        from app.actions.base_action import ActionOutput
        agent = self._make()
        output = agent.primary_action.run(object(), agent.llm_manager)
        self.assertIsInstance(output, ActionOutput)
        self.assertEqual(output.content, "")

    def test_research_returns_domain_brief(self):
        from app.shared.schemas.domain_schema import DomainBrief
        llm = _stub('{"domain": "e-commerce", "complexity": "medium"}')
        agent = self._make(llm)
        brief = agent.research("Build an online marketplace")
        self.assertIsInstance(brief, DomainBrief)
        self.assertEqual(brief.domain, "e-commerce")

    def test_research_degrades_gracefully_on_empty_json(self):
        from app.shared.schemas.domain_schema import DomainBrief
        llm = _stub("no json here at all")
        agent = self._make(llm)
        brief = agent.research("Build anything")
        self.assertIsInstance(brief, DomainBrief)
        self.assertEqual(brief.domain, "unknown")

    def test_research_degrades_gracefully_on_llm_error(self):
        from app.shared.schemas.domain_schema import DomainBrief

        class _FailingLLM:
            def generate_text(self, **kwargs):
                raise RuntimeError("LLM timeout")

        from app.agents.domain_researcher import DomainResearcherAgent
        agent = DomainResearcherAgent(llm_manager=_FailingLLM())
        brief = agent.research("Build anything")
        self.assertIsInstance(brief, DomainBrief)
        self.assertEqual(brief.domain, "unknown")

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "domain_research")


# ===========================================================================
# FilePlannerAgent
# ===========================================================================

class TestFilePlannerAgent(unittest.TestCase):

    def _make(self, llm=None, artifact_manager=None):
        from app.agents.file_planner import FilePlannerAgent
        return FilePlannerAgent(llm_manager=llm or _stub("{}"), artifact_manager=artifact_manager)

    def test_instantiates_without_llm(self):
        from app.agents.file_planner import FilePlannerAgent
        from app.actions.write_file_plan import WriteFilePlanAction
        agent = FilePlannerAgent()
        self.assertIsInstance(agent.primary_action, WriteFilePlanAction)

    def test_instantiates_with_artifact_manager(self):
        am = MagicMock()
        agent = self._make(artifact_manager=am)
        self.assertIs(agent._artifact_manager, am)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "file_plan")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "file_plan")

    def test_alias_file_structure_planner_agent(self):
        from app.agents.file_planner import FileStructurePlannerAgent, FilePlannerAgent
        self.assertIs(FileStructurePlannerAgent, FilePlannerAgent)


# ===========================================================================
# QAAgent
# ===========================================================================

class TestQAAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.qa import QAAgent
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])
        return QAAgent(
            llm_manager=llm or _stub("# generated tests"),
            project_writer=pw,
            project_reader=pr,
            file_validator=fv,
        )

    def test_instantiates_without_llm(self):
        from app.agents.qa import QAAgent
        from app.actions.write_qa_report import WriteQAReportAction
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        agent = QAAgent(project_reader=pr)
        self.assertIsInstance(agent.primary_action, WriteQAReportAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "qa")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "qa")

    def test_llm_receives_prompt(self):
        llm = _stub("# tests")
        self._make(llm).execute(_ctx("Test the payment module"))
        self.assertGreater(len(llm.calls), 0)


# ===========================================================================
# DevOpsAgent
# ===========================================================================

class TestDevOpsAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.devops import DevOpsAgent
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])
        return DevOpsAgent(
            llm_manager=llm or _stub("FROM python:3.11"),
            project_writer=pw,
            project_reader=pr,
            file_validator=fv,
        )

    def test_instantiates_without_llm(self):
        from app.agents.devops import DevOpsAgent
        from app.actions.write_deployment import WriteDeploymentAction
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        agent = DevOpsAgent(project_reader=pr)
        self.assertIsInstance(agent.primary_action, WriteDeploymentAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "devops")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "devops")


# ===========================================================================
# DocumentAgent
# ===========================================================================

class TestDocumentAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.document import DocumentAgent
        pw = MagicMock()
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        am = MagicMock()
        am.get_artifact.return_value = None
        return DocumentAgent(
            llm_manager=llm or _stub("# README"),
            project_writer=pw,
            project_reader=pr,
            artifact_manager=am,
        )

    def test_instantiates_without_llm(self):
        from app.agents.document import DocumentAgent
        from app.actions.write_documentation import WriteDocumentationAction
        pr = MagicMock()
        pr.read_project_files.return_value = {}
        agent = DocumentAgent(project_reader=pr)
        self.assertIsInstance(agent.primary_action, WriteDocumentationAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "document-output")

    def test_execute_returns_artifact(self):
        artifact = self._make().execute(_ctx())
        _assert_artifact(self, artifact, "document-output")


# ===========================================================================
# BackendDeveloperAgent
# ===========================================================================

class TestBackendDeveloperAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.backend import BackendDeveloperAgent
        pw = MagicMock()
        pw.write_file = MagicMock(return_value=None)
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])
        return BackendDeveloperAgent(
            llm_manager=llm or _stub("def main(): pass"),
            project_writer=pw,
            validator=fv,
        )

    def test_instantiates_without_llm(self):
        from app.agents.backend import BackendDeveloperAgent
        from app.actions.write_backend_code import WriteBackendCodeAction
        agent = BackendDeveloperAgent()
        self.assertIsInstance(agent.primary_action, WriteBackendCodeAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "backend")

    def test_max_attempts_constant(self):
        from app.agents.backend import BackendDeveloperAgent
        self.assertEqual(BackendDeveloperAgent.MAX_ATTEMPTS_PER_FILE, 3)

    def test_accepts_file_indexer(self):
        from app.agents.backend import BackendDeveloperAgent
        fi = MagicMock()
        agent = BackendDeveloperAgent(file_indexer=fi)
        self.assertIs(agent._file_indexer, fi)

    def test_execute_sprint_empty_file_plan_succeeds(self):
        from app.shared.schemas.file_plan_schema import FilePlan
        agent = self._make()
        plan = FilePlan(sprint_number=1, files={}, generation_order=[])
        result = agent.execute_sprint("proj-001", plan)
        self.assertTrue(result.success)
        self.assertEqual(result.written_files, [])

    def test_execute_sprint_generates_backend_files(self):
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec
        agent = self._make(_stub("def main(): pass"))
        plan = FilePlan(
            sprint_number=1,
            files={"backend/main.py": FileSpec(file_path="backend/main.py", language="python")},
            generation_order=["backend/main.py"],
        )
        result = agent.execute_sprint("proj-002", plan)
        self.assertTrue(result.success)
        self.assertEqual(len(result.written_files), 1)

    def test_execute_sprint_skips_non_backend_files(self):
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec
        agent = self._make()
        plan = FilePlan(
            sprint_number=1,
            files={"frontend/App.tsx": FileSpec(file_path="frontend/App.tsx", language="typescript")},
            generation_order=["frontend/App.tsx"],
        )
        result = agent.execute_sprint("proj-003", plan)
        self.assertTrue(result.success)
        self.assertEqual(result.written_files, [])

    def test_execute_sprint_records_failure_after_max_attempts(self):
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec

        fail_fv = MagicMock()
        fail_fv.validate.return_value = MagicMock(passed=False, errors=["syntax error"])
        from app.agents.backend import BackendDeveloperAgent
        agent = BackendDeveloperAgent(
            llm_manager=_stub("bad code!!!"),
            validator=fail_fv,
            project_writer=MagicMock(),
        )
        plan = FilePlan(
            sprint_number=1,
            files={"backend/broken.py": FileSpec(file_path="backend/broken.py", language="python")},
            generation_order=["backend/broken.py"],
        )
        result = agent.execute_sprint("proj-004", plan)
        self.assertFalse(result.success)
        self.assertEqual(len(result.failed_files), 1)


# ===========================================================================
# FrontendDeveloperAgent
# ===========================================================================

class TestFrontendDeveloperAgent(unittest.TestCase):

    def _make(self, llm=None):
        from app.agents.frontend import FrontendDeveloperAgent
        pw = MagicMock()
        pw.write_file = MagicMock(return_value=None)
        fv = MagicMock()
        fv.validate.return_value = MagicMock(passed=True, errors=[])
        return FrontendDeveloperAgent(
            llm_manager=llm or _stub("const App = () => <div/>;"),
            project_writer=pw,
            validator=fv,
        )

    def test_instantiates_without_llm(self):
        from app.agents.frontend import FrontendDeveloperAgent
        from app.actions.write_frontend_code import WriteFrontendCodeAction
        agent = FrontendDeveloperAgent()
        self.assertIsInstance(agent.primary_action, WriteFrontendCodeAction)

    def test_artifact_name(self):
        self.assertEqual(self._make().artifact_name, "frontend")

    def test_max_attempts_constant(self):
        from app.agents.frontend import FrontendDeveloperAgent
        self.assertEqual(FrontendDeveloperAgent.MAX_ATTEMPTS_PER_FILE, 3)

    def test_accepts_file_indexer(self):
        from app.agents.frontend import FrontendDeveloperAgent
        fi = MagicMock()
        agent = FrontendDeveloperAgent(file_indexer=fi)
        self.assertIs(agent._file_indexer, fi)

    def test_execute_sprint_empty_file_plan_succeeds(self):
        from app.shared.schemas.file_plan_schema import FilePlan
        agent = self._make()
        plan = FilePlan(sprint_number=1, files={}, generation_order=[])
        result = agent.execute_sprint("proj-005", plan)
        self.assertTrue(result.success)

    def test_execute_sprint_generates_frontend_files(self):
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec
        agent = self._make()
        plan = FilePlan(
            sprint_number=1,
            files={"frontend/App.tsx": FileSpec(file_path="frontend/App.tsx", language="typescript")},
            generation_order=["frontend/App.tsx"],
        )
        result = agent.execute_sprint("proj-006", plan)
        self.assertTrue(result.success)
        self.assertEqual(len(result.written_files), 1)

    def test_execute_sprint_skips_backend_files(self):
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec
        agent = self._make()
        plan = FilePlan(
            sprint_number=1,
            files={"backend/main.py": FileSpec(file_path="backend/main.py", language="python")},
            generation_order=["backend/main.py"],
        )
        result = agent.execute_sprint("proj-007", plan)
        self.assertTrue(result.success)
        self.assertEqual(result.written_files, [])


# ===========================================================================
# AgentFactory
# ===========================================================================

class TestAgentFactory(unittest.TestCase):

    REGISTERED_KEYS = [
        "product_owner", "architect", "backend", "frontend", "qa", "devops",
        "strategic_review", "designer", "security", "file_planner",
        "document", "retro", "clarification", "sprint_planner", "scrum_master",
    ]

    def setUp(self):
        from app.agents.factory import AgentFactory
        self.factory = AgentFactory()

    def test_all_agents_registered(self):
        for key in self.REGISTERED_KEYS:
            with self.subTest(key=key):
                self.assertTrue(self.factory.registry.has(key), f"{key} not registered")

    def test_create_product_owner(self):
        from app.agents.product_owner import ProductOwnerAgent
        self.assertIsInstance(self.factory.create("product_owner"), ProductOwnerAgent)

    def test_create_architect(self):
        from app.agents.architect import ArchitectAgent
        self.assertIsInstance(self.factory.create("architect"), ArchitectAgent)

    def test_create_strategic_review(self):
        from app.agents.strategic_review import StrategicReviewAgent
        self.assertIsInstance(self.factory.create("strategic_review"), StrategicReviewAgent)

    def test_create_designer(self):
        from app.agents.designer import DesignerAgent
        self.assertIsInstance(self.factory.create("designer"), DesignerAgent)

    def test_create_security(self):
        from app.agents.security import SecurityAgent
        self.assertIsInstance(self.factory.create("security"), SecurityAgent)

    def test_create_sprint_planner(self):
        from app.agents.sprint_planner import SprintPlannerAgent
        self.assertIsInstance(self.factory.create("sprint_planner"), SprintPlannerAgent)

    def test_create_scrum_master(self):
        from app.agents.scrum_master import ScrumMasterAgent
        self.assertIsInstance(self.factory.create("scrum_master"), ScrumMasterAgent)

    def test_create_file_planner(self):
        from app.agents.file_planner import FilePlannerAgent
        self.assertIsInstance(self.factory.create("file_planner"), FilePlannerAgent)

    def test_create_backend(self):
        from app.agents.backend import BackendDeveloperAgent
        self.assertIsInstance(self.factory.create("backend"), BackendDeveloperAgent)

    def test_create_frontend(self):
        from app.agents.frontend import FrontendDeveloperAgent
        self.assertIsInstance(self.factory.create("frontend"), FrontendDeveloperAgent)

    def test_create_qa(self):
        from app.agents.qa import QAAgent
        self.assertIsInstance(self.factory.create("qa"), QAAgent)

    def test_create_devops(self):
        from app.agents.devops import DevOpsAgent
        self.assertIsInstance(self.factory.create("devops"), DevOpsAgent)

    def test_create_document(self):
        from app.agents.document import DocumentAgent
        self.assertIsInstance(self.factory.create("document"), DocumentAgent)

    def test_create_retro(self):
        from app.agents.retro import RetroAgent
        self.assertIsInstance(self.factory.create("retro"), RetroAgent)

    def test_create_clarification(self):
        from app.agents.clarification import ClarificationAgent
        self.assertIsInstance(self.factory.create("clarification"), ClarificationAgent)

    def test_create_by_camelcase_architect(self):
        from app.agents.architect import ArchitectAgent
        self.assertIsInstance(self.factory.create("Architect"), ArchitectAgent)

    def test_create_unknown_raises(self):
        from app.shared.exceptions import DependencyException
        with self.assertRaises((DependencyException, Exception)):
            self.factory.create("nonexistent_agent_xyz")

    def test_create_returns_new_instance_each_call(self):
        a1 = self.factory.create("architect")
        a2 = self.factory.create("architect")
        self.assertIsNot(a1, a2)


# ===========================================================================
# AgentRegistry
# ===========================================================================

class TestAgentRegistry(unittest.TestCase):

    def setUp(self):
        from app.agents.registry import AgentRegistry
        self.registry = AgentRegistry()

    def test_register_and_has(self):
        self.registry.register("test_key", object)
        self.assertTrue(self.registry.has("test_key"))

    def test_has_returns_false_for_unknown(self):
        self.assertFalse(self.registry.has("does_not_exist"))

    def test_resolve_returns_registered_class(self):
        self.registry.register("my_agent", str)
        resolved = self.registry.resolve("my_agent")
        self.assertIs(resolved, str)

    def test_register_overwrites_existing_key(self):
        self.registry.register("key", str)
        self.registry.register("key", int)
        self.assertIs(self.registry.resolve("key"), int)


# ===========================================================================
# AgentResolver (stage name normalization)
# ===========================================================================

class TestAgentResolver(unittest.TestCase):

    def setUp(self):
        from app.agents.resolver import AgentResolver
        self.resolver = AgentResolver()

    def test_lowercase_passthrough(self):
        self.assertEqual(self.resolver.resolve("architect"), "architect")

    def test_camelcase_to_snake(self):
        resolved = self.resolver.resolve("ProductOwner")
        self.assertEqual(resolved, "product_owner")

    def test_architect_camelcase(self):
        resolved = self.resolver.resolve("Architect")
        self.assertEqual(resolved, "architect")

    def test_backend_developer_camelcase(self):
        resolved = self.resolver.resolve("BackendDeveloper")
        self.assertEqual(resolved, "backend")

    def test_strategic_review_camelcase(self):
        resolved = self.resolver.resolve("StrategicReview")
        self.assertEqual(resolved, "strategic_review")


# ===========================================================================
# BaseAction: extract_json
# ===========================================================================

class TestBaseActionExtractJson(unittest.TestCase):

    def setUp(self):
        from app.actions.base_action import BaseAction
        self.extract = BaseAction.extract_json

    def test_parses_plain_json(self):
        result = self.extract('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_parses_fenced_json(self):
        result = self.extract('```json\n{"key": "val"}\n```')
        self.assertEqual(result, {"key": "val"})

    def test_returns_empty_dict_on_no_json(self):
        result = self.extract("no json in this response at all")
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_empty_string(self):
        result = self.extract("")
        self.assertEqual(result, {})

    def test_nested_json(self):
        result = self.extract('{"a": {"b": 1}}')
        self.assertEqual(result["a"]["b"], 1)


if __name__ == "__main__":
    unittest.main()

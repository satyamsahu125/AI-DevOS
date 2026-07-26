"""Tests for the Five Sprint-Sync Fixes.

FIX 1  — DomainResearcherAgent + DomainResearchPromptBuilder + DomainBrief schema
FIX 2  — Q&A pipeline synchronization (verified correct, no code changes needed)
FIX 3  — SprintMonitor (generate_sprint_brief + validate_sprint_output)
FIX 4  — ImpactAnalyzer.analyze_file_impact() (file-level partial change analysis)
FIX 5  — BackendDeveloperAgent._build_file_prompt() sprint_brief + summary threshold
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# FIX 1 — DomainBrief schema
# ---------------------------------------------------------------------------

class TestDomainBriefSchema:
    def test_default_values(self):
        from app.shared.schemas.domain_schema import DomainBrief
        brief = DomainBrief()
        assert brief.domain == ""
        assert brief.complexity == "medium"
        assert brief.standard_modules == []
        assert brief.standard_actors == []
        assert brief.standard_integrations == []
        assert brief.common_pitfalls == []
        assert brief.regulatory_concerns == []
        assert brief.questions_to_ask == []
        assert brief.questions_not_to_ask == []
        assert brief.comparable_products == []
        assert brief.anything_unusual == ""

    def test_all_fields_populated(self):
        from app.shared.schemas.domain_schema import DomainBrief
        data = {
            "domain": "food delivery",
            "complexity": "high",
            "standard_modules": ["menu", "cart", "order"],
            "standard_actors": ["customer", "restaurant", "driver"],
            "standard_integrations": ["Stripe", "Google Maps"],
            "common_pitfalls": ["GPS drift", "payment timeouts"],
            "regulatory_concerns": ["PCI-DSS", "GDPR"],
            "questions_to_ask": ["Will restaurants self-manage menus?"],
            "questions_not_to_ask": ["Do you need a database?"],
            "comparable_products": ["Swiggy", "Uber Eats"],
            "anything_unusual": "Multi-currency support required",
        }
        brief = DomainBrief.model_validate(data)
        assert brief.domain == "food delivery"
        assert brief.complexity == "high"
        assert "menu" in brief.standard_modules
        assert "Stripe" in brief.standard_integrations
        assert "PCI-DSS" in brief.regulatory_concerns
        assert brief.anything_unusual == "Multi-currency support required"

    def test_partial_data_uses_defaults(self):
        from app.shared.schemas.domain_schema import DomainBrief
        brief = DomainBrief.model_validate({"domain": "e-commerce"})
        assert brief.domain == "e-commerce"
        assert brief.complexity == "medium"
        assert brief.standard_modules == []

    def test_model_dump_roundtrip(self):
        from app.shared.schemas.domain_schema import DomainBrief
        original = DomainBrief(
            domain="healthcare",
            complexity="high",
            standard_modules=["patient", "appointment"],
        )
        dumped = original.model_dump()
        restored = DomainBrief.model_validate(dumped)
        assert restored.domain == original.domain
        assert restored.standard_modules == original.standard_modules


# ---------------------------------------------------------------------------
# FIX 1 — DomainResearchPromptBuilder
# ---------------------------------------------------------------------------

class TestDomainResearchPromptBuilder:
    def test_build_research_prompt_contains_request(self):
        from app.prompt.domain_research_builder import DomainResearchPromptBuilder
        builder = DomainResearchPromptBuilder()
        prompt = builder.build_research_prompt("Build a telemedicine app")
        assert "telemedicine" in prompt

    def test_system_prompt_is_non_empty(self):
        from app.prompt.domain_research_builder import DomainResearchPromptBuilder
        builder = DomainResearchPromptBuilder()
        assert len(builder.system_prompt) > 100

    def test_system_prompt_mentions_json(self):
        from app.prompt.domain_research_builder import DomainResearchPromptBuilder
        builder = DomainResearchPromptBuilder()
        assert "JSON" in builder.system_prompt or "json" in builder.system_prompt.lower()

    def test_prompt_template_inserts_request(self):
        from app.prompt.domain_research_builder import DomainResearchPromptBuilder
        builder = DomainResearchPromptBuilder()
        request = "Build a parking management system with IoT sensors"
        prompt = builder.build_research_prompt(request)
        assert request in prompt


# ---------------------------------------------------------------------------
# FIX 1 — DomainResearcherAgent
# ---------------------------------------------------------------------------

class TestDomainResearcherAgent:
    def _make_agent(self, llm_response_content: str):
        from app.agents.domain_researcher import DomainResearcherAgent
        llm = MagicMock()
        llm.generate_text.return_value = MagicMock(content=llm_response_content)
        agent = DomainResearcherAgent(llm_manager=llm)
        return agent

    def test_returns_domain_brief_on_valid_json(self):
        from app.shared.schemas.domain_schema import DomainBrief
        payload = '{"domain": "food delivery", "complexity": "high", "standard_modules": ["cart", "order"]}'
        agent = self._make_agent(payload)
        result = agent.research("Build a food delivery app")
        assert isinstance(result, DomainBrief)
        assert result.domain == "food delivery"
        assert result.complexity == "high"

    def test_graceful_degradation_on_llm_error(self):
        from app.agents.domain_researcher import DomainResearcherAgent
        from app.shared.schemas.domain_schema import DomainBrief
        llm = MagicMock()
        llm.generate_text.side_effect = RuntimeError("LLM timeout")
        agent = DomainResearcherAgent(llm_manager=llm)
        result = agent.research("Build something")
        assert isinstance(result, DomainBrief)
        assert result.domain == "unknown"
        assert result.complexity == "medium"

    def test_graceful_degradation_on_invalid_json(self):
        from app.shared.schemas.domain_schema import DomainBrief
        agent = self._make_agent("Sorry, I cannot process this request.")
        result = agent.research("Build something")
        assert isinstance(result, DomainBrief)
        assert result.domain == "unknown"

    def test_graceful_degradation_on_malformed_json(self):
        from app.shared.schemas.domain_schema import DomainBrief
        agent = self._make_agent('{"domain": "food"')  # truncated JSON
        result = agent.research("Build something")
        assert isinstance(result, DomainBrief)

    def test_populates_questions_to_ask(self):
        payload = """{
            "domain": "logistics",
            "complexity": "medium",
            "questions_to_ask": ["How many warehouses?", "Real-time tracking?"],
            "questions_not_to_ask": ["Do you need login?"]
        }"""
        agent = self._make_agent(payload)
        result = agent.research("Build a logistics platform")
        assert "How many warehouses?" in result.questions_to_ask
        assert "Do you need login?" in result.questions_not_to_ask


# ---------------------------------------------------------------------------
# FIX 1 — ClarificationBuilder domain_brief injection
# ---------------------------------------------------------------------------

class TestClarificationBuilderDomainInjection:
    def test_build_generate_prompt_without_domain_brief(self):
        from app.prompt.clarification_builder import ClarificationPromptBuilder
        builder = ClarificationPromptBuilder()
        prompt = builder.build_generate_prompt("Build a task manager")
        assert "Build a task manager" in prompt

    def test_build_generate_prompt_with_domain_brief_injects_domain(self):
        from app.prompt.clarification_builder import ClarificationPromptBuilder
        builder = ClarificationPromptBuilder()
        brief = {
            "domain": "project management",
            "complexity": "medium",
            "standard_modules": ["tasks", "boards", "users"],
            "standard_actors": ["team member", "admin"],
            "questions_to_ask": ["Kanban or Scrum?"],
            "questions_not_to_ask": ["Do you need a database?"],
            "common_pitfalls": ["Overcomplicating the task model"],
        }
        prompt = builder.build_generate_prompt("Build a task manager", domain_brief=brief)
        assert "project management" in prompt
        assert "tasks" in prompt or "standard_modules" in prompt.lower() or "tasks" in prompt

    def test_domain_brief_none_falls_back_to_plain_prompt(self):
        from app.prompt.clarification_builder import ClarificationPromptBuilder
        builder = ClarificationPromptBuilder()
        plain = builder.build_generate_prompt("Build a task manager")
        with_none = builder.build_generate_prompt("Build a task manager", domain_brief=None)
        assert plain == with_none

    def test_domain_brief_empty_dict_falls_back_to_plain_prompt(self):
        from app.prompt.clarification_builder import ClarificationPromptBuilder
        builder = ClarificationPromptBuilder()
        plain = builder.build_generate_prompt("Build a task manager")
        with_empty = builder.build_generate_prompt("Build a task manager", domain_brief={})
        assert plain == with_empty

    def test_domain_brief_questions_not_to_ask_appear_in_prompt(self):
        from app.prompt.clarification_builder import ClarificationPromptBuilder
        builder = ClarificationPromptBuilder()
        brief = {
            "domain": "food delivery",
            "questions_not_to_ask": ["Do you need authentication?"],
        }
        prompt = builder.build_generate_prompt("Build a food app", domain_brief=brief)
        assert "authentication" in prompt.lower() or "questions_not_to_ask" in prompt.lower() or "Do you need authentication?" in prompt


# ---------------------------------------------------------------------------
# FIX 3 — SprintMonitor
# ---------------------------------------------------------------------------

class TestSprintMonitorFirstSprint:
    def _make_monitor(self, indexed_files=None):
        from app.intelligence.sprint_monitor import SprintMonitor
        indexer = MagicMock()
        indexer.get_project_index.return_value = indexed_files or []
        indexer.get_file_summary.return_value = "summary text"
        dep_graph = MagicMock()
        dep_graph.get_most_depended_on.return_value = []
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = None
        workspace = MagicMock()
        return SprintMonitor(indexer, dep_graph, artifact_manager, workspace)

    def test_first_sprint_brief_contains_no_previous_files(self):
        monitor = self._make_monitor(indexed_files=[])
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=1, sprint_goal="Build auth")
        assert "FIRST sprint" in brief or "no previous" in brief.lower()

    def test_first_sprint_brief_contains_sprint_number(self):
        monitor = self._make_monitor(indexed_files=[])
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=1, sprint_goal="Build auth")
        assert "1" in brief

    def test_first_sprint_brief_contains_goal(self):
        monitor = self._make_monitor(indexed_files=[])
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=1, sprint_goal="Implement user login")
        assert "Implement user login" in brief


class TestSprintMonitorSubsequentSprint:
    def _make_file(self, path: str, sprint_num: int, classes=None):
        meta = MagicMock()
        meta.file_path = path
        meta.sprint_number = sprint_num
        meta.classes = classes or []
        return meta

    def _make_monitor(self, built_files, critical_files=None, arch_content=None):
        from app.intelligence.sprint_monitor import SprintMonitor
        indexer = MagicMock()
        indexer.get_project_index.return_value = built_files
        indexer.get_file_summary.side_effect = lambda pid, fp: f"[summary of {fp}]"
        dep_graph = MagicMock()
        dep_graph.get_most_depended_on.return_value = critical_files or []
        artifact = MagicMock()
        if arch_content:
            artifact.structured_content = arch_content
        else:
            artifact.structured_content = None
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = artifact
        workspace = MagicMock()
        return SprintMonitor(indexer, dep_graph, artifact_manager, workspace)

    def test_subsequent_sprint_brief_lists_previous_files(self):
        built = [
            self._make_file("backend/auth.py", sprint_num=1),
            self._make_file("backend/models.py", sprint_num=1),
        ]
        monitor = self._make_monitor(built)
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=2, sprint_goal="Build API")
        assert "PREVIOUS" in brief or "previous" in brief.lower() or "2 files" in brief

    def test_subsequent_sprint_brief_contains_critical_files(self):
        built = [self._make_file("backend/auth.py", sprint_num=1)]
        critical = [("backend/models.py", 5)]
        monitor = self._make_monitor(built, critical_files=critical)
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=2, sprint_goal="Build API")
        assert "CRITICAL" in brief or "models.py" in brief

    def test_subsequent_sprint_brief_contains_instructions(self):
        built = [self._make_file("backend/auth.py", sprint_num=1)]
        monitor = self._make_monitor(built)
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=2, sprint_goal="Build API")
        assert "DO NOT recreate" in brief or "do not" in brief.lower()

    def test_sprint_2_only_sees_sprint_1_files(self):
        """Sprint 3 brief should only see sprints 1 and 2 files, not sprint 3."""
        built = [
            self._make_file("backend/auth.py", sprint_num=1),
            self._make_file("backend/payments.py", sprint_num=2),
            self._make_file("backend/reports.py", sprint_num=3),  # current sprint
        ]
        monitor = self._make_monitor(built)
        brief = monitor.generate_sprint_brief("proj-1", sprint_number=3, sprint_goal="Build reports")
        # The brief should mention 2 previous files (sprint 1 and 2), not 3
        assert "reports.py" not in brief or "2 files" in brief


class TestSprintMonitorValidation:
    def _make_file(self, path, sprint_num, classes=None):
        meta = MagicMock()
        meta.file_path = path
        meta.sprint_number = sprint_num
        meta.classes = classes or []
        return meta

    def test_validate_returns_empty_when_no_arch_artifact(self):
        from app.intelligence.sprint_monitor import SprintMonitor
        indexer = MagicMock()
        indexer.get_project_index.return_value = []
        dep_graph = MagicMock()
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = None
        monitor = SprintMonitor(indexer, dep_graph, artifact_manager, MagicMock())
        issues = monitor.validate_sprint_output("proj-1", sprint_number=1)
        assert issues == []

    def test_validate_detects_missing_model(self):
        from app.intelligence.sprint_monitor import SprintMonitor
        built = [self._make_file("backend/user.py", 1, classes=["UserService"])]
        indexer = MagicMock()
        indexer.get_project_index.return_value = built
        dep_graph = MagicMock()
        arch = MagicMock()
        arch.structured_content = {
            "data_models": [
                {"name": "User"},
                {"name": "Payment"},  # Payment not in any class
            ]
        }
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = arch
        monitor = SprintMonitor(indexer, dep_graph, artifact_manager, MagicMock())
        issues = monitor.validate_sprint_output("proj-1", sprint_number=1)
        assert any("payment" in i.lower() for i in issues)

    def test_validate_no_issues_when_all_models_present(self):
        from app.intelligence.sprint_monitor import SprintMonitor
        built = [self._make_file("backend/models.py", 1, classes=["User", "Payment"])]
        indexer = MagicMock()
        indexer.get_project_index.return_value = built
        dep_graph = MagicMock()
        arch = MagicMock()
        arch.structured_content = {
            "data_models": [{"name": "User"}, {"name": "Payment"}]
        }
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = arch
        monitor = SprintMonitor(indexer, dep_graph, artifact_manager, MagicMock())
        issues = monitor.validate_sprint_output("proj-1", sprint_number=1)
        assert issues == []

    def test_validate_returns_empty_when_no_data_models_in_arch(self):
        from app.intelligence.sprint_monitor import SprintMonitor
        indexer = MagicMock()
        indexer.get_project_index.return_value = []
        dep_graph = MagicMock()
        arch = MagicMock()
        arch.structured_content = {"data_models": []}
        artifact_manager = MagicMock()
        artifact_manager.get_artifact.return_value = arch
        monitor = SprintMonitor(indexer, dep_graph, artifact_manager, MagicMock())
        issues = monitor.validate_sprint_output("proj-1", sprint_number=1)
        assert issues == []


# ---------------------------------------------------------------------------
# FIX 4 — ImpactAnalyzer.analyze_file_impact()
# ---------------------------------------------------------------------------

class TestAnalyzeFileImpact:
    def _make_analyzer(self, relevant_files=None, dep_impact=None, built_files=None):
        from app.workflow.impact_analyzer import ImpactAnalyzer

        code_summarizer = MagicMock()
        code_summarizer.get_relevant_files.return_value = relevant_files or []

        dep_graph = MagicMock()
        dep_graph.get_impact.side_effect = lambda pid, fp: dep_impact or []

        file_meta = []
        for path in (built_files or []):
            m = MagicMock()
            m.file_path = path
            file_meta.append(m)
        file_indexer = MagicMock()
        file_indexer.get_project_index.return_value = file_meta

        return ImpactAnalyzer(
            llm_manager=MagicMock(),
            artifact_manager=MagicMock(),
            file_indexer=file_indexer,
            dep_graph=dep_graph,
            code_summarizer=code_summarizer,
        )

    def test_returns_dict_with_required_keys(self):
        analyzer = self._make_analyzer()
        result = analyzer.analyze_file_impact("proj-1", "Add payment module")
        assert "files_to_regenerate" in result
        assert "files_safe" in result
        assert "total_affected" in result
        assert "total_preserved" in result
        assert "explanation" in result

    def test_no_intelligence_layer_returns_not_available(self):
        from app.workflow.impact_analyzer import ImpactAnalyzer
        analyzer = ImpactAnalyzer(
            llm_manager=MagicMock(),
            artifact_manager=MagicMock(),
        )
        result = analyzer.analyze_file_impact("proj-1", "Add payment module")
        assert result["total_affected"] == 0
        assert "not available" in result["explanation"].lower() or "not wired" in result["explanation"].lower()

    def test_identifies_directly_relevant_files(self):
        relevant = ["backend/payment.py"]
        built = ["backend/payment.py", "backend/user.py", "backend/order.py"]
        analyzer = self._make_analyzer(relevant_files=relevant, built_files=built)
        result = analyzer.analyze_file_impact("proj-1", "Change payment flow")
        assert "backend/payment.py" in result["files_to_regenerate"]

    def test_expands_via_dependency_graph(self):
        relevant = ["backend/payment.py"]
        dep_impact = ["backend/order.py"]  # order.py depends on payment.py
        built = ["backend/payment.py", "backend/order.py", "backend/user.py"]
        analyzer = self._make_analyzer(
            relevant_files=relevant,
            dep_impact=dep_impact,
            built_files=built,
        )
        result = analyzer.analyze_file_impact("proj-1", "Change payment flow")
        assert "backend/order.py" in result["files_to_regenerate"]

    def test_unaffected_files_go_to_files_safe(self):
        relevant = ["backend/payment.py"]
        built = ["backend/payment.py", "backend/user.py"]
        analyzer = self._make_analyzer(relevant_files=relevant, built_files=built)
        result = analyzer.analyze_file_impact("proj-1", "Change payment flow")
        assert "backend/user.py" in result["files_safe"]

    def test_counts_match_lists(self):
        relevant = ["backend/payment.py"]
        built = ["backend/payment.py", "backend/user.py", "backend/order.py"]
        analyzer = self._make_analyzer(relevant_files=relevant, built_files=built)
        result = analyzer.analyze_file_impact("proj-1", "Change payment flow")
        assert result["total_affected"] == len(result["files_to_regenerate"])
        assert result["total_preserved"] == len(result["files_safe"])

    def test_explanation_is_human_readable(self):
        relevant = ["backend/auth.py"]
        built = ["backend/auth.py"]
        analyzer = self._make_analyzer(relevant_files=relevant, built_files=built)
        result = analyzer.analyze_file_impact("proj-1", "Change auth logic")
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 0

    def test_error_in_summarizer_returns_safe_fallback(self):
        from app.workflow.impact_analyzer import ImpactAnalyzer
        code_summarizer = MagicMock()
        code_summarizer.get_relevant_files.side_effect = RuntimeError("DB error")
        analyzer = ImpactAnalyzer(
            llm_manager=MagicMock(),
            artifact_manager=MagicMock(),
            file_indexer=MagicMock(),
            dep_graph=MagicMock(),
            code_summarizer=code_summarizer,
        )
        result = analyzer.analyze_file_impact("proj-1", "Change auth logic")
        assert "error" in result["explanation"].lower()
        assert result["files_to_regenerate"] == []


# ---------------------------------------------------------------------------
# FIX 5 — BackendDeveloperAgent._build_file_prompt() summary threshold
# ---------------------------------------------------------------------------

class TestBackendAgentFileSummaryThreshold:
    def _make_agent(self, file_content: str, file_summary: str | None = None):
        from app.agents.backend import BackendDeveloperAgent
        from app.shared.schemas.file_plan_schema import FilePlan, FileSpec

        writer = MagicMock()
        writer.read_file.return_value = file_content

        file_indexer = MagicMock()
        file_indexer.get_file_summary.return_value = file_summary

        agent = BackendDeveloperAgent(
            project_writer=writer,
            file_indexer=file_indexer,
        )
        return agent, writer, file_indexer

    def _make_file_spec(self, dep_paths: list[str]):
        from app.shared.schemas.file_plan_schema import FileSpec
        spec = FileSpec(file_path="backend/service.py", language="python")
        spec.depends_on = dep_paths
        spec.purpose = "Test service"
        spec.required_imports = []
        spec.required_classes = ""
        spec.required_functions = ""
        spec.exports = ""
        return spec

    def _make_file_plan(self):
        from app.shared.schemas.file_plan_schema import FilePlan
        plan = MagicMock()
        plan.sprint_number = 1
        plan.tech_stack = "FastAPI, PostgreSQL"
        plan.generation_order = []
        plan.files = {}
        return plan

    def test_small_dep_sends_full_content(self):
        short_content = "x = 1  # small file"
        agent, writer, indexer = self._make_agent(short_content)
        spec = self._make_file_spec(["backend/utils.py"])
        plan = self._make_file_plan()
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1)
        assert short_content in prompt
        indexer.get_file_summary.assert_not_called()

    def test_large_dep_uses_summary(self):
        large_content = "x" * 2000  # exceeds 1500-char threshold
        summary = "[summary: DatabaseService class with connect(), query(), close()]"
        agent, writer, indexer = self._make_agent(large_content, file_summary=summary)
        spec = self._make_file_spec(["backend/db.py"])
        plan = self._make_file_plan()
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1)
        assert summary in prompt
        assert large_content not in prompt

    def test_large_dep_truncates_when_no_indexer(self):
        from app.agents.backend import BackendDeveloperAgent
        large_content = "x" * 2000
        writer = MagicMock()
        writer.read_file.return_value = large_content
        agent = BackendDeveloperAgent(project_writer=writer, file_indexer=None)

        from app.shared.schemas.file_plan_schema import FileSpec
        spec = FileSpec(file_path="backend/service.py", language="python")
        spec.depends_on = ["backend/db.py"]
        spec.purpose = "test"
        spec.required_imports = []
        spec.required_classes = ""
        spec.required_functions = ""
        spec.exports = ""
        plan = self._make_file_plan()
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1)
        assert "first 1500 chars" in prompt
        # full large content not pasted verbatim
        assert large_content not in prompt

    def test_sprint_brief_prepended_to_prompt(self):
        agent, writer, _ = self._make_agent("small content")
        spec = self._make_file_spec([])
        plan = self._make_file_plan()
        sprint_brief = "SPRINT 2 BRIEF\nGoal: Add payments\n"
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1, sprint_brief=sprint_brief)
        assert prompt.startswith(sprint_brief)

    def test_no_sprint_brief_no_prepend(self):
        agent, writer, _ = self._make_agent("small content")
        spec = self._make_file_spec([])
        plan = self._make_file_plan()
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1, sprint_brief="")
        assert not prompt.startswith("SPRINT")

    def test_previous_error_injected_into_prompt(self):
        agent, writer, _ = self._make_agent("small content")
        spec = self._make_file_spec([])
        plan = self._make_file_plan()
        error_msg = "SyntaxError: unexpected EOF"
        prompt = agent._build_file_prompt(spec, plan, "proj-1", error_msg, 2)
        assert error_msg in prompt


# ---------------------------------------------------------------------------
# FIX 5 — FrontendDeveloperAgent._build_file_prompt() same contract
# ---------------------------------------------------------------------------

class TestFrontendAgentFileSummaryThreshold:
    def _make_agent(self, file_content: str, file_summary: str | None = None):
        from app.agents.frontend import FrontendDeveloperAgent
        writer = MagicMock()
        writer.read_file.return_value = file_content
        file_indexer = MagicMock()
        file_indexer.get_file_summary.return_value = file_summary
        agent = FrontendDeveloperAgent(project_writer=writer, file_indexer=file_indexer)
        return agent, writer, file_indexer

    def _make_file_spec(self, dep_paths: list[str]):
        from app.shared.schemas.file_plan_schema import FileSpec
        spec = FileSpec(file_path="frontend/components/Button.tsx", language="typescript")
        spec.depends_on = dep_paths
        spec.purpose = "Test component"
        spec.required_imports = []
        spec.required_classes = ""
        spec.required_functions = ""
        spec.exports = ""
        return spec

    def _make_plan(self):
        plan = MagicMock()
        plan.sprint_number = 1
        plan.tech_stack = "React, TypeScript"
        return plan

    def test_large_dep_uses_summary(self):
        large_content = "y" * 2000
        summary = "[summary: useAuth hook — returns {user, login, logout}]"
        agent, writer, indexer = self._make_agent(large_content, file_summary=summary)
        spec = self._make_file_spec(["frontend/hooks/useAuth.ts"])
        plan = self._make_plan()
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1)
        assert summary in prompt
        assert large_content not in prompt

    def test_sprint_brief_prepended(self):
        agent, writer, _ = self._make_agent("small")
        spec = self._make_file_spec([])
        plan = self._make_plan()
        brief = "SPRINT 2 BRIEF\nGoal: Build UI\n"
        prompt = agent._build_file_prompt(spec, plan, "proj-1", "", 1, sprint_brief=brief)
        assert prompt.startswith(brief)

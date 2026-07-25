import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.actions.base_action import ActionOutput, BaseAction, LLMAction
from app.actions.write_requirements import WriteRequirementsAction
from app.agents.product_owner import ProductOwnerAgent
from app.llm.llm_response import LLMResponse as RichLLMResponse
from app.shared.schemas.requirements_schema import RequirementsArtifact


class _StubLLMManager:
    """Fake LLMManager returning a fixed response, so actions never depend on a live Ollama server."""

    def __init__(self, content: str, usage: dict | None = None, latency: float = 0.05) -> None:
        self._content = content
        self._usage = usage or {"prompt": 10, "completion": 5, "total": 15}
        self._latency = latency
        self.last_stage: str | None = None
        self.last_agent: str | None = None

    def generate_text(self, prompt: str, system_prompt: str = "", model=None, stage: str = "", agent: str = "", **kwargs) -> RichLLMResponse:
        self.last_stage = stage
        self.last_agent = agent
        return RichLLMResponse(
            response_id="r1",
            provider="stub",
            model="stub-model",
            content=self._content,
            usage=self._usage,
            latency=self._latency,
        )


class ActionLayerTests(unittest.TestCase):
    def test_base_action_extract_json_handles_fenced_and_raw_and_missing(self) -> None:
        self.assertEqual(BaseAction.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(BaseAction.extract_json('some text\n```json\n{"a": 2}\n```\nmore text'), {"a": 2})
        self.assertEqual(BaseAction.extract_json("no json here at all"), {})
        self.assertEqual(BaseAction.extract_json(""), {})

    def test_write_requirements_action_produces_validated_structured_output(self) -> None:
        payload = {
            "project_name": "Demo",
            "goals": ["ship a todo API"],
            "user_stories": ["as a user I can add a task"],
            "acceptance_criteria": ["POST /tasks returns 201"],
            "constraints": [],
            "out_of_scope": [],
        }
        llm = _StubLLMManager(content=json.dumps(payload))
        action = WriteRequirementsAction()

        output = action.run(SimpleNamespace(content="build a todo API"), llm)

        self.assertIsInstance(output, ActionOutput)
        self.assertEqual(output.structured["project_name"], "Demo")
        RequirementsArtifact.model_validate(output.structured)  # does not raise
        self.assertEqual(output.tokens_used, 15)
        self.assertGreater(output.latency_ms, 0)
        self.assertEqual(llm.last_stage, "WriteRequirements")

    def test_write_requirements_action_tolerates_non_json_response(self) -> None:
        llm = _StubLLMManager(content="Sure, here are the requirements: build a login page.")
        action = WriteRequirementsAction()

        output = action.run(SimpleNamespace(content="build a login page"), llm)

        self.assertIsInstance(output.structured, dict)
        self.assertIn("login page", output.content)

    def test_action_falls_back_to_measured_latency_when_response_has_none(self) -> None:
        class _NoLatencyLLM:
            def generate_text(self, prompt, system_prompt="", model=None, **kwargs):
                return SimpleNamespace(content="{}", usage={}, latency=None)

        action = WriteRequirementsAction()
        output = action.run(SimpleNamespace(content="x"), _NoLatencyLLM())
        self.assertGreaterEqual(output.latency_ms, 0)

    def test_base_agent_execute_delegates_to_primary_action(self) -> None:
        payload = {"project_name": "CRM", "goals": ["track leads"], "user_stories": [], "acceptance_criteria": [], "constraints": [], "out_of_scope": []}
        llm = _StubLLMManager(content=json.dumps(payload))
        agent = ProductOwnerAgent(llm_manager=llm)

        artifact = agent.execute(SimpleNamespace(content="build a CRM"))

        self.assertEqual(artifact.name, "product-owner-output")
        self.assertEqual(artifact.schema_type, "WriteRequirements")
        self.assertEqual(artifact.structured_content["project_name"], "CRM")

    def test_llm_action_is_a_base_action(self) -> None:
        self.assertTrue(issubclass(LLMAction, BaseAction))


if __name__ == "__main__":
    unittest.main()

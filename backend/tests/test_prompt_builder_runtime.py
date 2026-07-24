import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.context.context import AgentContext
from app.memory.memory_summary import MemorySummary
from app.prompt.prompt_builder_runtime import PromptBuilderRuntime
from app.prompt.prompt_template import PromptTemplate
from app.prompt.prompt_validator import PromptValidationException
from app.prompt.prompt_variables import PromptVariables


class PromptBuilderRuntimeTests(unittest.TestCase):
    def test_builds_prompt_package_with_resolved_content(self) -> None:
        template = PromptTemplate(
            template_id="tmpl-1",
            agent="backend",
            stage="planning",
            system="System {{task}}",
            user="User {{name}}",
            rules="Rules {{rule}}",
        )
        runtime = PromptBuilderRuntime()
        package = runtime.build(
            template,
            PromptVariables({"task": "analyze", "name": "Ada", "rule": "be clear"}),
            context=AgentContext(project_name="demo", requirements="reqs", architecture="arch"),
            memory_summary=MemorySummary(summary="remember me"),
        )

        self.assertEqual(package.system_prompt, "System analyze")
        self.assertEqual(package.user_prompt, "User Ada")
        self.assertEqual(package.rules_prompt, "Rules be clear")
        self.assertGreater(package.estimated_tokens, 0)
        self.assertEqual(package.metadata["agent"], "backend")

    def test_rejects_missing_variables(self) -> None:
        template = PromptTemplate(
            template_id="tmpl-2",
            agent="qa",
            stage="review",
            system="System {{task}}",
            user="User {{name}}",
        )
        runtime = PromptBuilderRuntime()

        with self.assertRaises(PromptValidationException):
            runtime.build(template, PromptVariables({"task": "review"}))


if __name__ == "__main__":
    unittest.main()

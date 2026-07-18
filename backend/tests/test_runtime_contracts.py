import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.backend import BackendDeveloperAgent
from app.agents.devops import DevOpsAgent
from app.agents.frontend import FrontendDeveloperAgent
from app.agents.qa import QAAgent
from app.artifact.metadata import ArtifactMetadata
from app.context.context import AgentContext
from app.execution.dependency_resolver import DependencyResolver
from app.execution.execution_plan import ExecutionPlan
from app.execution.scheduler import ExecutionScheduler
from app.llm.factory import LLMFactory
from app.prompt.architect_builder import ArchitectPromptBuilder
from app.prompt.backend_builder import BackendPromptBuilder
from app.prompt.devops_builder import DevOpsPromptBuilder
from app.prompt.frontend_builder import FrontendPromptBuilder
from app.prompt.qa_builder import QAPromptBuilder
from app.prompt.renderer import PromptRenderer
from app.prompt.template import PromptTemplate
from app.prompt.validator import PromptValidator
from app.review.result import ReviewResult
from app.review.rules import ReviewRules
from app.review.validator import ReviewValidator
from app.workflow.dependency_graph import DependencyGraph
from app.workflow.retry_policy import RetryPolicy
from app.workflow.state_machine import WorkflowStateMachine


class RuntimeContractsTests(unittest.TestCase):
    def test_prompt_and_review_runtime_contracts(self) -> None:
        template = PromptTemplate(name="test", system_template="Hello {name}", user_template="{topic}")
        renderer = PromptRenderer()
        self.assertEqual(renderer.render(template, {"name": "Ada"}), "Hello Ada")

        validator = PromptValidator()
        self.assertTrue(validator.validate(template))

        review_result = ReviewResult(approved=True, score=1.0, feedback="ok", retry_required=False, reviewer="reviewer")
        self.assertTrue(review_result.approved)

        review_validator = ReviewValidator()
        self.assertTrue(review_validator.validate(review_result))

        rules = ReviewRules()
        self.assertTrue(rules.is_approved(review_result))

        resolver = DependencyResolver()
        self.assertTrue(resolver.can_execute("product_owner", []))
        self.assertEqual(resolver.next_stage([]), "product_owner")

        scheduler = ExecutionScheduler()
        plan = ExecutionPlan(workflow_id="wf", stages=["product_owner"], current_stage="product_owner", completed_stages=[], failed_stages=[], metadata={})
        self.assertEqual(scheduler.schedule(plan), "product_owner")

        state_machine = WorkflowStateMachine()
        state_machine.start()
        self.assertEqual(state_machine.state.value, "Running")

        graph = DependencyGraph()
        self.assertTrue(graph.has_dependency("product_owner"))

        retry_policy = RetryPolicy(max_retries=1)
        self.assertTrue(retry_policy.should_retry(0))

        context = AgentContext(project_name="demo", requirements="reqs", architecture="arch")
        self.assertEqual(context.project_name, "demo")

        architect_builder = ArchitectPromptBuilder()
        backend_builder = BackendPromptBuilder()
        frontend_builder = FrontendPromptBuilder()
        qa_builder = QAPromptBuilder()
        devops_builder = DevOpsPromptBuilder()
        self.assertTrue(callable(architect_builder.build))
        self.assertTrue(callable(backend_builder.build))
        self.assertTrue(callable(frontend_builder.build))
        self.assertTrue(callable(qa_builder.build))
        self.assertTrue(callable(devops_builder.build))

        metadata = ArtifactMetadata(artifact_id="a1", name="artifact", location=Path("/tmp/out.txt"), version=1, status="Stored")
        self.assertEqual(metadata.version, 1)

        factory = LLMFactory()
        self.assertEqual(factory.create_provider("ollama").__class__.__name__, "OllamaProvider")

        backend_agent = BackendDeveloperAgent()
        frontend_agent = FrontendDeveloperAgent()
        qa_agent = QAAgent()
        devops_agent = DevOpsAgent()
        self.assertEqual(backend_agent.execute(context).name, "backend")
        self.assertEqual(frontend_agent.execute(context).name, "frontend")
        self.assertEqual(qa_agent.execute(context).name, "qa")
        self.assertEqual(devops_agent.execute(context).name, "devops")


if __name__ == "__main__":
    unittest.main()

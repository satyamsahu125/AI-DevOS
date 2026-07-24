import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact
from app.shared.schemas.architecture_schema import APIEndpoint, ArchitectureArtifact, DataModel, ModuleSpec
from app.shared.schemas.code_schema import CodeArtifact, CodeFile
from app.shared.schemas.deployment_schema import DeploymentArtifact, DeploymentStep
from app.shared.schemas.message import AgentMessage
from app.shared.schemas.qa_schema import Bug, QAArtifact, TestCase
from app.shared.schemas.requirements_schema import RequirementsArtifact


class StructuredArtifactSchemaTests(unittest.TestCase):
    def test_requirements_artifact_round_trips_through_json(self) -> None:
        artifact = RequirementsArtifact(
            project_name="Demo",
            goals=["ship a todo API"],
            user_stories=["as a user I can add a task"],
            acceptance_criteria=["POST /tasks returns 201"],
            constraints=["must use SQLite"],
            out_of_scope=["mobile app"],
        )
        restored = RequirementsArtifact.model_validate_json(artifact.model_dump_json())
        self.assertEqual(restored, artifact)

    def test_architecture_artifact_nested_models(self) -> None:
        artifact = ArchitectureArtifact(
            approach="modular monolith",
            modules=[ModuleSpec(name="api", purpose="http layer", dependencies=["core"])],
            api_design=[APIEndpoint(path="/tasks", method="POST", request="TaskCreate", response="Task")],
            data_models=[DataModel(name="Task", fields=["id", "title"])],
            tech_stack={"backend": "FastAPI"},
        )
        self.assertEqual(artifact.modules[0].name, "api")
        self.assertEqual(artifact.api_design[0].method, "POST")
        self.assertEqual(artifact.tech_stack["backend"], "FastAPI")

    def test_code_artifact_files(self) -> None:
        artifact = CodeArtifact(
            files=[CodeFile(filename="main.py", language="python", content="print('hi')", purpose="entry point")],
            entry_point="main.py",
            dependencies=["fastapi"],
        )
        self.assertEqual(artifact.files[0].filename, "main.py")
        self.assertIn("fastapi", artifact.dependencies)

    def test_qa_artifact_bugs_and_tests(self) -> None:
        artifact = QAArtifact(
            test_cases=[TestCase(name="test_add", steps=["POST /tasks"], expected="201", actual="201", status="pass")],
            coverage_percent=87.5,
            bugs_found=[Bug(id="BUG-1", severity="low", description="typo", file="main.py", line=10)],
            regression_tests=["test_add"],
        )
        self.assertEqual(artifact.coverage_percent, 87.5)
        self.assertEqual(artifact.bugs_found[0].severity, "low")

    def test_deployment_artifact(self) -> None:
        artifact = DeploymentArtifact(
            steps=[DeploymentStep(name="build", command="docker build .", description="build image")],
            environment={"ENV": "production"},
            rollback_plan="redeploy previous image",
        )
        self.assertEqual(artifact.steps[0].name, "build")

    def test_agent_message_requires_a_valid_stage(self) -> None:
        message = AgentMessage(
            role="product_owner",
            stage=Stage.ProductOwner,
            content="requirements drafted",
            structured={"goals": ["ship it"]},
            cause_by="WriteRequirements",
        )
        self.assertEqual(message.stage, Stage.ProductOwner)
        restored = AgentMessage.model_validate_json(message.model_dump_json())
        self.assertEqual(restored.content, "requirements drafted")

    def test_stage_artifact_has_schema_type_and_structured_content(self) -> None:
        artifact = StageArtifact(
            artifact_id="a1",
            name="product-owner-output",
            content="{}",
            schema_type="WriteRequirements",
            structured_content={"goals": []},
        )
        self.assertEqual(artifact.schema_type, "WriteRequirements")
        self.assertEqual(artifact.structured_content, {"goals": []})

    def test_stage_artifact_structured_content_defaults_empty(self) -> None:
        artifact = StageArtifact(artifact_id="a2", name="qa", content="content")
        self.assertEqual(artifact.schema_type, "")
        self.assertEqual(artifact.structured_content, {})


if __name__ == "__main__":
    unittest.main()

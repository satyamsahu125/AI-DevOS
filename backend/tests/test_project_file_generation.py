import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.backend import BackendDeveloperAgent
from app.agents.frontend import FrontendDeveloperAgent
from app.artifact.manager import ArtifactManager
from app.llm.response import LLMResponse
from app.review.reviewer import Reviewer
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact
from app.workspace.manager import WorkspaceManager
from app.workspace.project_files import ProjectFileManager

_ARCHITECTURE = {
    "approach": "modular monolith",
    "modules": [{"name": "api", "purpose": "http layer", "dependencies": []}],
    "api_design": [{"path": "/tasks", "method": "GET", "request": "", "response": ""}],
    "data_models": [{"name": "Task", "fields": ["id", "title"]}],
    "tech_stack": {"backend": "FastAPI", "frontend": "React"},
}

_FILE_PLAN = {
    "files": [
        {"path": "main.py", "module": "api", "purpose": "FastAPI entry point", "responsible_stage": "backend"},
        {"path": "models.py", "module": "api", "purpose": "Task data model", "responsible_stage": "backend"},
        {"path": "src/App.jsx", "module": "ui", "purpose": "root component", "responsible_stage": "frontend"},
    ],
}


class _ScriptedLLMManager:
    """Fake LLMManager returning one scripted response per call, in call order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate_text(self, prompt: str, system_prompt: str = "", **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        content = self._responses.pop(0) if self._responses else ""
        return LLMResponse(content=content, model="stub", finish_reason="stop", input_tokens=0, output_tokens=0, total_tokens=3)


class _Rig:
    """Isolated ArtifactManager/WorkspaceManager/ProjectFileManager stack rooted at a fresh temp dir,
    seeded with an approved Architecture and File Plan for "proj1"."""

    def __init__(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="project_file_gen_"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.artifact_manager = ArtifactManager(
            storage_dir=self.tmp_dir / "artifacts", workspace_manager=self.workspace_manager, db_path=self.tmp_dir / "memory.db",
        )
        self.project_file_manager = ProjectFileManager(self.workspace_manager)
        self.workspace_manager.create_workspace("proj1")
        self.artifact_manager.save_artifact("proj1", Stage.Architect, "arch", structured_content=_ARCHITECTURE, attempt=1)
        self.artifact_manager.save_artifact("proj1", Stage.FileStructurePlanner, "plan", structured_content=_FILE_PLAN, attempt=1)

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


class ProjectFileManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="project_file_manager_"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.manager = ProjectFileManager(self.workspace_manager)
        self.workspace_manager.create_workspace("proj1")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_file_creates_real_file_under_project_area(self) -> None:
        written = self.manager.write_file("proj1", "backend", "app/main.py", "print('hi')")

        self.assertTrue(written.absolute_path.exists())
        self.assertEqual(written.absolute_path.read_text(encoding="utf-8"), "print('hi')")
        expected = self.workspace_manager.get_workspace_path("proj1") / "project" / "backend" / "app" / "main.py"
        self.assertEqual(written.absolute_path, expected)

    def test_write_file_can_overwrite_a_previous_attempt(self) -> None:
        self.manager.write_file("proj1", "backend", "main.py", "version 1")
        written = self.manager.write_file("proj1", "backend", "main.py", "version 2")

        self.assertEqual(written.absolute_path.read_text(encoding="utf-8"), "version 2")

    def test_list_written_returns_relative_forward_slashed_paths(self) -> None:
        self.manager.write_file("proj1", "backend", "main.py", "x")
        self.manager.write_file("proj1", "backend", "routers/tasks.py", "y")

        self.assertEqual(self.manager.list_written("proj1", "backend"), ["main.py", "routers/tasks.py"])

    def test_list_written_empty_for_unwritten_area(self) -> None:
        self.assertEqual(self.manager.list_written("proj1", "frontend"), [])

    def test_areas_stay_isolated_from_each_other(self) -> None:
        self.manager.write_file("proj1", "backend", "main.py", "backend file")
        self.manager.write_file("proj1", "frontend", "main.py", "frontend file")

        self.assertEqual(self.manager.list_written("proj1", "backend"), ["main.py"])
        self.assertEqual(self.manager.list_written("proj1", "frontend"), ["main.py"])

    def test_leading_slash_path_stays_inside_project_area(self) -> None:
        """Regression test: Path("area") / "/x/y" is ABSOLUTE in pathlib and silently discards
        "area" -- this used to write real "recipe box" project files outside the project
        directory entirely (confirmed live: FileStructurePlanner emitted "/api/users/register"
        style paths and GET /projects/{id}/files came back empty despite a "written: 5/5" manifest)."""
        written = self.manager.write_file("proj1", "backend", "/api/users/register", "handler code")

        expected = self.workspace_manager.get_workspace_path("proj1") / "project" / "backend" / "api" / "users" / "register"
        self.assertEqual(written.absolute_path, expected)
        self.assertEqual(written.path, "api/users/register")
        self.assertEqual(self.manager.list_written("proj1", "backend"), ["api/users/register"])

    def test_backslash_path_is_normalized_to_forward_slashes(self) -> None:
        written = self.manager.write_file("proj1", "backend", "routers\\tasks.py", "x")
        self.assertEqual(written.path, "routers/tasks.py")

    def test_path_traversal_is_rejected(self) -> None:
        from app.execution.safety_policy import SafetyException

        with self.assertRaises(SafetyException):
            self.manager.write_file("proj1", "backend", "../../etc/passwd", "malicious")
        self.assertNotEqual(
            self.manager.area_dir("proj1", "backend") / "main.py",
            self.manager.area_dir("proj1", "frontend") / "main.py",
        )


class BackendFrontendFileGenerationTests(unittest.TestCase):
    def test_backend_agent_writes_only_backend_assigned_files(self) -> None:
        rig = _Rig()
        try:
            llm = _ScriptedLLMManager(["def main() -> None:\n    print('main')", "class Task: pass  # model"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            artifact = agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

            self.assertEqual(len(llm.prompts), 2)
            self.assertIn("main.py", llm.prompts[1])  # second prompt lists main.py as an already-written sibling
            self.assertEqual(rig.project_file_manager.list_written("proj1", "backend"), ["main.py", "models.py"])
            self.assertEqual(rig.project_file_manager.list_written("proj1", "frontend"), [])
            self.assertEqual(artifact.structured_content["written_paths"], ["main.py", "models.py"])
            self.assertEqual(artifact.structured_content["skipped_paths"], [])
        finally:
            rig.cleanup()

    def test_plan_path_already_prefixed_with_area_is_not_doubled(self) -> None:
        rig = _Rig()
        try:
            rig.workspace_manager.create_workspace("proj-prefixed")
            rig.artifact_manager.save_artifact("proj-prefixed", Stage.Architect, "arch", structured_content=_ARCHITECTURE, attempt=1)
            rig.artifact_manager.save_artifact(
                "proj-prefixed", Stage.FileStructurePlanner, "plan", attempt=1,
                structured_content={"files": [
                    {"path": "backend/models/Task.js", "module": "api", "purpose": "task model", "responsible_stage": "backend"},
                ]},
            )
            llm = _ScriptedLLMManager(["const Task = {};\nmodule.exports = Task;"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            agent.execute(SimpleNamespace(content="build a todo app", project_id="proj-prefixed"))

            written = rig.project_file_manager.list_written("proj-prefixed", "backend")
            self.assertEqual(written, ["models/Task.js"])
            expected_path = rig.project_file_manager.area_dir("proj-prefixed", "backend") / "models" / "Task.js"
            self.assertTrue(expected_path.exists())
            self.assertFalse((rig.project_file_manager.area_dir("proj-prefixed", "backend") / "backend").exists())
        finally:
            rig.cleanup()

    def test_frontend_agent_writes_only_frontend_assigned_files(self) -> None:
        rig = _Rig()
        try:
            llm = _ScriptedLLMManager(["export default function App() { return null; }"])
            agent = FrontendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

            self.assertEqual(rig.project_file_manager.list_written("proj1", "frontend"), ["src/App.jsx"])
            self.assertEqual(rig.project_file_manager.list_written("proj1", "backend"), [])
        finally:
            rig.cleanup()

    def test_code_fence_wrapped_response_is_unwrapped_before_writing(self) -> None:
        rig = _Rig()
        try:
            fenced = "```python\ndef main() -> None:\n    print('hi')\n```"
            llm = _ScriptedLLMManager([fenced, "class Task: pass  # model"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

            written_path = rig.project_file_manager.area_dir("proj1", "backend") / "main.py"
            self.assertEqual(written_path.read_text(encoding="utf-8"), "def main() -> None:\n    print('hi')")
        finally:
            rig.cleanup()

    def test_implausible_response_is_skipped_not_written(self) -> None:
        rig = _Rig()
        try:
            llm = _ScriptedLLMManager(["ok", "class Task: pass"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            artifact = agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

            self.assertEqual(rig.project_file_manager.list_written("proj1", "backend"), ["models.py"])
            self.assertEqual(artifact.structured_content["skipped_paths"], ["main.py"])
        finally:
            rig.cleanup()

    def test_backend_auto_generates_package_json_from_real_imports(self) -> None:
        """The whole point of run-instructions/download being useful: `npm install` needs a real
        package.json, so this shouldn't just be advice in a README -- the file has to actually
        exist, listing whatever the generated files really import."""
        rig = _Rig()
        try:
            rig.workspace_manager.create_workspace("proj-node")
            rig.artifact_manager.save_artifact("proj-node", Stage.Architect, "arch", structured_content=_ARCHITECTURE, attempt=1)
            rig.artifact_manager.save_artifact(
                "proj-node", Stage.FileStructurePlanner, "plan", attempt=1,
                structured_content={"files": [
                    {"path": "routes/tasks.js", "module": "api", "purpose": "task routes", "responsible_stage": "backend"},
                ]},
            )
            llm = _ScriptedLLMManager(["const express = require('express');\nmodule.exports = express.Router();"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            agent.execute(SimpleNamespace(content="build a todo app", project_id="proj-node"))

            written = rig.project_file_manager.list_written("proj-node", "backend")
            self.assertIn("package.json", written)
            package_json_path = rig.project_file_manager.area_dir("proj-node", "backend") / "package.json"
            payload = json.loads(package_json_path.read_text(encoding="utf-8"))
            self.assertIn("express", payload["dependencies"])
        finally:
            rig.cleanup()

    def test_no_manifest_generated_when_no_external_imports_found(self) -> None:
        rig = _Rig()
        try:
            llm = _ScriptedLLMManager(["def main() -> None:\n    print('main')", "class Task: pass  # model"])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

            self.assertNotIn("requirements.txt", rig.project_file_manager.list_written("proj1", "backend"))
        finally:
            rig.cleanup()

    def test_no_file_plan_produces_empty_manifest_and_writes_nothing(self) -> None:
        rig = _Rig()
        try:
            rig.workspace_manager.create_workspace("proj-empty")
            rig.artifact_manager.save_artifact("proj-empty", Stage.Architect, "arch", structured_content=_ARCHITECTURE, attempt=1)
            llm = _ScriptedLLMManager([])
            agent = BackendDeveloperAgent(llm_manager=llm, artifact_manager=rig.artifact_manager, project_file_manager=rig.project_file_manager)

            artifact = agent.execute(SimpleNamespace(content="build a todo app", project_id="proj-empty"))

            self.assertEqual(llm.prompts, [])
            self.assertEqual(rig.project_file_manager.list_written("proj-empty", "backend"), [])
            self.assertIn("No backend-assigned files", artifact.content)
        finally:
            rig.cleanup()


class CodeStageReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviewer = Reviewer()

    def _artifact(self, structured: dict, schema_type: str = "WriteBackendFiles") -> StageArtifact:
        return StageArtifact(artifact_id="a1", name="backend", content="# Backend Developer Manifest", schema_type=schema_type, structured_content=structured)

    def test_full_coverage_approves(self) -> None:
        result = self.reviewer.review(self._artifact({
            "planned_paths": ["main.py", "models.py"], "written_paths": ["main.py", "models.py"], "skipped_paths": [],
        }))
        self.assertTrue(result.approved)

    def test_skipped_files_block_approval(self) -> None:
        result = self.reviewer.review(self._artifact({
            "planned_paths": ["main.py", "models.py"], "written_paths": ["main.py"], "skipped_paths": ["models.py"],
        }))
        self.assertFalse(result.approved)
        self.assertTrue(any("models.py" in q for q in result.human_questions))

    def test_no_planned_files_asks_human(self) -> None:
        result = self.reviewer.review(self._artifact({"planned_paths": [], "written_paths": [], "skipped_paths": []}))
        self.assertFalse(result.approved)
        self.assertTrue(any("File Plan" in q for q in result.human_questions))

    def test_low_coverage_flags_even_when_written_files_are_all_that_was_attempted(self) -> None:
        result = self.reviewer.review(self._artifact({
            "planned_paths": ["a.py", "b.py", "c.py"], "written_paths": ["a.py"], "skipped_paths": ["b.py", "c.py"],
        }))
        self.assertTrue(any("planned files were written" in flag for flag in result.flags))


if __name__ == "__main__":
    unittest.main()

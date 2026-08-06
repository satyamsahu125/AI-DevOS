from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

from .base_action import ActionOutput, BaseAction
from ..execution.file_validator import FileValidator
from ..execution.project_reader import ProjectReader
from ..execution.project_writer import ProjectWriter
from ..prompt.qa_builder import QAPromptBuilder

logger = logging.getLogger(__name__)


class WriteQAReportAction(BaseAction):
    """Generates real pytest test files and runs them.

    Writes test files to project/tests/ directory. Returns structured output with both
    files and test results.
    """

    name = "WriteQAReport"
    description = "Generates real pytest test files and executes them against backend."

    def __init__(
        self,
        prompt_builder: QAPromptBuilder | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
        file_validator: FileValidator | None = None,
    ) -> None:
        self.project_writer = project_writer or ProjectWriter()
        self.project_reader = project_reader or ProjectReader()
        self.file_validator = file_validator or FileValidator()
        self.prompt_builder = prompt_builder or QAPromptBuilder(self.project_reader)
        super().__init__()

    def run(self, context: Any, llm: Any) -> ActionOutput:
        """Generate test files and run them."""
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        prompt_str = self.prompt_builder.build(context)

        system_prompt = getattr(self.prompt_builder, "SYSTEM_PROMPT", None) or "You are a Senior QA Engineer writing real pytest files."
        response = llm.generate_text(
            prompt=prompt_str,
            system_prompt=system_prompt,
            max_tokens=4096,
        )
        if not isinstance(response, str):
            response = getattr(response, "content", str(response))

        test_files = self._parse_file_blocks(response)

        if not test_files:
            logger.error("QA agent produced no parseable test files")
            return ActionOutput(
                content="QA generation failed — no files produced",
                structured={},
                tokens_used=0,
                latency_ms=0,
            )

        written_files = []
        for file_path, content in test_files.items():
            validation = self.file_validator.validate(
                file_path=file_path,
                content=content,
                language="python",
            )

            if validation.passed:
                written = self.project_writer.write_file(
                    project_id=project_id,
                    file_path=file_path,
                    content=content,
                )
                written_files.append(written)
                logger.info("Written test file: %s", file_path)
            else:
                # Still write if minor syntax warning or force write fallback
                written = self.project_writer.write_file(
                    project_id=project_id,
                    file_path=file_path,
                    content=content,
                )
                written_files.append(written)
                logger.warning("Test file written with validation warnings: %s — %s", file_path, validation.errors)

        test_results = self._run_tests(project_id)

        structured = {
            "test_files_written": [f.file_path for f in written_files],
            "test_results": test_results,
            "total_tests": test_results.get("total", 0),
            "passed": test_results.get("passed", 0),
            "failed": test_results.get("failed", 0),
            "errors": test_results.get("errors", []),
        }

        summary = (
            f"QA Complete: {structured['passed']}/{structured['total_tests']}"
            f" tests passing. "
            f"Files: {', '.join(structured['test_files_written'])}"
        )

        return ActionOutput(
            content=summary,
            structured=structured,
            tokens_used=0,
            latency_ms=0,
        )

    def _parse_file_blocks(self, response: str) -> dict[str, str]:
        """Parse ===FILE: path=== ... ===END=== blocks from LLM response.

        Returns dict of {file_path: content}
        """
        files = {}
        pattern = r"===FILE:\s*(.+?)===\n(.*?)===END==="
        matches = re.findall(pattern, response, re.DOTALL)

        for file_path, content in matches:
            file_path = file_path.strip()
            content = content.strip()
            if file_path and content:
                files[file_path] = content
                logger.info("Parsed test file: %s (%d chars)", file_path, len(content))

        if not files:
            if "import pytest" in response or "def test_" in response:
                files["tests/test_api.py"] = response
                logger.warning("No file blocks found, treating content as tests/test_api.py")

        return files

    def _run_tests(self, project_id: str) -> dict:
        """Run pytest against the generated test files.

        Copies test files to a system temp directory before running so that
        pytest output (bytecode, .pytest_cache) is never written inside the
        uvicorn watch root.  Using sys.executable ensures the correct venv
        python is used regardless of how the server was started.

        Returns results dict with pass/fail counts.
        """
        import shutil
        import sys
        import tempfile

        project_dir = self.project_reader.get_project_dir(project_id)
        tests_dir = project_dir / "tests"

        if not tests_dir.exists() or not any(tests_dir.glob("test_*.py")):
            logger.warning("No test files to run for %s", project_id)
            return {"total": 0, "passed": 0, "failed": 0, "errors": []}

        # Copy tests to a temp dir outside uvicorn's watch root so that
        # file-system changes during the run don't trigger a server reload.
        tmp_dir: str | None = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="devos_qa_")
            tmp_tests = str(tmp_dir)
            shutil.copytree(str(tests_dir), tmp_tests, dirs_exist_ok=True)

            env = {
                **__import__("os").environ,
                "PYTHONDONTWRITEBYTECODE": "1",  # no .pyc files
                "PYTHONPATH": str(project_dir),
            }

            result = subprocess.run(
                [
                    sys.executable, "-m", "pytest",
                    tmp_tests,
                    "--tb=short", "--no-header", "-q",
                    # Disable cache so no .pytest_cache is written
                    "-p", "no:cacheprovider",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tmp_tests,
                env=env,
            )

            output = result.stdout + result.stderr
            return self._parse_pytest_output(output, result.returncode)

        except subprocess.TimeoutExpired:
            logger.error("pytest timed out for project %s", project_id)
            return {"total": 0, "passed": 0, "failed": 0, "errors": ["Tests timed out after 60s"]}
        except Exception as e:
            logger.error("Failed to run tests: %s", str(e))
            return {"total": 0, "passed": 0, "failed": 0, "errors": [str(e)]}
        finally:
            if tmp_dir:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

    def _parse_pytest_output(self, output: str, returncode: int) -> dict:
        """Parse pytest -q output to extract pass/fail counts."""
        results = {"total": 0, "passed": 0, "failed": 0, "errors": [], "output": output[:2000]}

        summary = re.search(r"(\d+) passed(?:, (\d+) failed)?", output)
        if summary:
            results["passed"] = int(summary.group(1))
            results["failed"] = int(summary.group(2) or 0)
            results["total"] = results["passed"] + results["failed"]

        failed_tests = re.findall(r"FAILED (.+?) -", output)
        results["failed_tests"] = failed_tests
        results["all_passed"] = returncode == 0

        logger.info("Test results: %d/%d passed", results["passed"], results["total"])
        return results

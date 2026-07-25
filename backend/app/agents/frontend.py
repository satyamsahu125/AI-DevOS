from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_frontend_code import WriteFrontendCodeAction
from ..artifact.manager import ArtifactManager
from ..execution.file_validator import FileValidator
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.frontend_builder import FrontendPromptBuilder
from ..shared.dto.sprint_execution import FileGenerationResult, SprintExecutionResult
from ..shared.schemas.file_plan_schema import FilePlan, FileSpec
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FrontendDeveloperAgent(BaseAgent):
    """Generates frontend code file by file.

    Each LLM call produces clean code files. Validates before writing. Retries
    with error feedback. Writes real files to temp-workspace/{id}/project/
    """

    MAX_ATTEMPTS_PER_FILE = 3
    artifact_name = "frontend"

    def __init__(
        self,
        prompt_builder: FrontendPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
        project_writer: ProjectWriter | None = None,
        validator: FileValidator | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._artifact_manager = artifact_manager
        self._project_file_manager = project_file_manager
        self.project_writer = project_writer or ProjectWriter(workspace_manager)
        self.validator = validator or FileValidator()
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return WriteFrontendCodeAction(self._prompt_builder, self._artifact_manager, self._project_file_manager)

    def execute_sprint(
        self,
        project_id: str,
        file_plan: FilePlan,
        context: object | None = None,
        design_artifact: dict | str | None = None,
    ) -> SprintExecutionResult:
        """Execute all frontend files in this sprint.

        design_artifact is the approved design spec; when provided it is
        injected into every file prompt so no frontend code is written
        without it. None keeps the prompt unchanged.
        """
        written_files = []
        failed_files = []

        gen_order = getattr(file_plan, "generation_order", []) or []
        files_map = getattr(file_plan, "files", {}) or {}

        frontend_files = [fp for fp in gen_order if fp.startswith("frontend/")]
        if not frontend_files and files_map:
            frontend_files = [fp for fp in files_map if fp.startswith("frontend/")]

        for file_path in frontend_files:
            file_spec = files_map.get(file_path) or FileSpec(file_path=file_path, language="typescript")
            result = self._generate_one_file(
                project_id=project_id,
                file_path=file_path,
                file_spec=file_spec,
                file_plan=file_plan,
                context=context,
                design_artifact=design_artifact,
            )
            if result.success:
                written_files.append(result)
            else:
                failed_files.append(result)
                logger.error(
                    "Failed to generate: %s after %d attempts", file_path, self.MAX_ATTEMPTS_PER_FILE
                )

        return SprintExecutionResult(
            sprint_number=file_plan.sprint_number,
            written_files=written_files,
            failed_files=failed_files,
            success=len(failed_files) == 0,
        )

    def _generate_one_file(
        self,
        project_id: str,
        file_path: str,
        file_spec: FileSpec,
        file_plan: FilePlan,
        context: object | None,
        design_artifact: dict | str | None = None,
    ) -> FileGenerationResult:
        """Generate, validate, and write ONE file."""
        last_error = ""

        for attempt in range(1, self.MAX_ATTEMPTS_PER_FILE + 1):
            prompt = self._build_file_prompt(
                file_spec=file_spec,
                file_plan=file_plan,
                project_id=project_id,
                previous_error=last_error,
                attempt=attempt,
                design_artifact=design_artifact,
            )

            response = self.llm_manager.generate_text(
                prompt=prompt,
                system_prompt=self._file_system_prompt(),
                stage="frontend",
                project_id=project_id,
            )
            raw_content = getattr(response, "content", str(response))
            content = self._extract_code(raw_content)

            validation = self.validator.validate(
                file_path=file_path,
                content=content,
                language=file_spec.language or "typescript",
            )

            if validation.passed:
                written = self.project_writer.write_file(
                    project_id=project_id,
                    file_path=file_path,
                    content=content,
                    attempt=attempt,
                )
                logger.info("✓ Generated: %s (attempt %d)", file_path, attempt)
                return FileGenerationResult(
                    file_path=file_path,
                    success=True,
                    attempts=attempt,
                    written_file=written,
                )
            else:
                last_error = "\n".join(validation.errors)
                logger.warning("✗ Validation failed attempt %d: %s — %s", attempt, file_path, last_error)

        return FileGenerationResult(
            file_path=file_path,
            success=False,
            attempts=self.MAX_ATTEMPTS_PER_FILE,
            last_error=last_error,
        )

    def _build_file_prompt(
        self,
        file_spec: FileSpec,
        file_plan: FilePlan,
        project_id: str,
        previous_error: str,
        attempt: int,
        design_artifact: dict | str | None = None,
    ) -> str:
        """Build prompt for ONE file generation, including the approved design spec."""
        design_context = self._build_design_context(design_artifact)
        dependency_context = ""
        deps = getattr(file_spec, "depends_on", []) or []
        for dep_path in deps[:3]:
            dep_content = self.project_writer.read_file(project_id, dep_path)
            if dep_content:
                dependency_context += f"\n\n// {dep_path}:\n{dep_content}"

        error_context = ""
        if previous_error:
            error_context = f"\nPREVIOUS ATTEMPT FAILED WITH THESE ERRORS:\n{previous_error}\nFix these errors in your response.\n"

        req_imports = "\n".join(f"  - {imp}" for imp in (getattr(file_spec, "required_imports", []) or []))

        return f"""
Generate the file: {file_spec.file_path}

Purpose: {file_spec.purpose}
Language: {file_spec.language}
Tech stack: {file_plan.tech_stack}

Required imports (must include all of these):
{req_imports}

Required components / classes to implement:
{file_spec.required_classes}

Required functions / hooks to implement:
{file_spec.required_functions}

Exports from this file:
{file_spec.exports}

These dependency files already exist (for context):
{dependency_context}
{design_context}
{error_context}
Write ONLY the complete {file_spec.file_path} file.
No explanation. No markdown. No code fences. Just the code.
"""

    def _build_design_context(self, design_artifact: dict | str | None) -> str:
        """Render the approved design spec into a prompt block.

        Returns "" when there is no design, leaving the prompt unchanged.
        A non-dict design (raw Designer text that never parsed as JSON) is
        passed through verbatim rather than dropped.
        """
        if not design_artifact:
            return ""
        if not isinstance(design_artifact, dict):
            return (
                "\nAPPROVED DESIGN SPECIFICATION (implement exactly this):\n"
                f"{str(design_artifact)[:2000]}\n"
            )

        components = design_artifact.get("components") or []
        pages = design_artifact.get("pages") or []
        palette = design_artifact.get("color_palette") or {}

        component_lines = "\n".join(
            f"  - {component.get('name', '')}: {component.get('shadcn_component', '')}"
            f" classes={component.get('tailwind_classes', '')}"
            for component in components[:10]
            if isinstance(component, dict)
        )
        page_names = [page.get("name", "") for page in pages if isinstance(page, dict)]

        return (
            "\nAPPROVED DESIGN SPECIFICATION (implement exactly this):\n"
            f"  Color palette: {palette}\n"
            f"  Typography: {design_artifact.get('typography', {})}\n"
            f"  Border radius: {design_artifact.get('border_radius', '')}\n"
            f"  Pages: {page_names}\n"
            f"  Components to implement:\n{component_lines}\n"
        )

    def _file_system_prompt(self) -> str:
        return """
You are an expert React/TypeScript frontend developer.
You generate production-quality code files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences (no ```typescript)
- No explanations before or after
- Include ALL required imports
- Implement ALL required components and functions
- Follow the exact interface specified
- Use TypeScript type annotations everywhere
- Use clean, modern Tailwind CSS styling
"""

    def _extract_code(self, response: str) -> str:
        """Strip any accidental markdown fences."""
        content = response.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content

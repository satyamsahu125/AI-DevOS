from __future__ import annotations

import logging
import re
from typing import Any

from .base_action import ActionOutput, BaseAction
from ..execution.file_validator import FileValidator
from ..execution.project_reader import ProjectReader
from ..prompt.devops_builder import DevOpsPromptBuilder

logger = logging.getLogger(__name__)


class WriteDeploymentAction(BaseAction):
    """Generates DevOps configuration files as structured output.

    Does NOT write files directly. Returns structured output with file contents
    for the ExecutionEngine to write via FileCommand (single write path).
    """

    name = "WriteDeployment"
    description = "Produce Dockerfile, docker-compose.yml, .env.example, and CI configuration files."

    def __init__(
        self,
        prompt_builder: DevOpsPromptBuilder | None = None,
        project_reader: ProjectReader | None = None,
        file_validator: FileValidator | None = None,
    ) -> None:
        self.project_reader = project_reader or ProjectReader()
        self.file_validator = file_validator or FileValidator()
        self.prompt_builder = prompt_builder or DevOpsPromptBuilder(self.project_reader)
        super().__init__()

    def run(self, context: Any, llm: Any) -> ActionOutput:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        prompt_str = self.prompt_builder.build(context)
        system_prompt = getattr(self.prompt_builder, "SYSTEM_PROMPT", None) or "You are a DevOps Engineer writing Docker and CI configs."

        response = llm.generate_text(
            prompt=prompt_str,
            system_prompt=system_prompt,
            max_tokens=4096,
        )
        if not isinstance(response, str):
            response = getattr(response, "content", str(response))

        config_files = self._parse_file_blocks(response)

        validation_errors = []

        for file_path, content in config_files.items():
            language = "yaml" if file_path.endswith((".yml", ".yaml")) else ("dockerfile" if "Dockerfile" in file_path else "text")

            if language == "yaml":
                validation = self.file_validator.validate(
                    file_path=file_path,
                    content=content,
                    language="yaml",
                )
                if not validation.passed:
                    validation_errors.extend(validation.errors)
                    logger.warning("YAML validation error for %s: %s", file_path, validation.errors)

        structured = {
            "files": config_files,
            "validation_errors": validation_errors,
            "has_dockerfile": any("Dockerfile" in p for p in config_files),
            "has_compose": any("docker-compose" in p for p in config_files),
            "has_ci": any("ci.yml" in p or ".github" in p for p in config_files),
        }

        summary = (
            f"DevOps Complete: {len(config_files)} files generated. "
            f"Dockerfile: {structured['has_dockerfile']}, "
            f"Compose: {structured['has_compose']}, "
            f"CI: {structured['has_ci']}"
        )

        return ActionOutput(
            content=summary,
            structured=structured,
            tokens_used=0,
            latency_ms=0,
        )

    def _parse_file_blocks(self, response: str) -> dict[str, str]:
        """Parse ===FILE: path=== ... ===END=== blocks from LLM response."""
        files = {}
        pattern = r"===FILE:\s*(.+?)===\n(.*?)===END==="
        matches = re.findall(pattern, response, re.DOTALL)

        for file_path, content in matches:
            file_path = file_path.strip()
            content = content.strip()
            if file_path and content:
                files[file_path] = content

        if not files:
            # Fallback if markdown format or single block
            if "FROM python" in response or "services:" in response:
                files["Dockerfile"] = response

        return files

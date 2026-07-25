from __future__ import annotations

import logging
from typing import Any

from .base_action import ActionOutput, BaseAction
from ..artifact.manager import ArtifactManager
from ..execution.project_reader import ProjectReader
from ..execution.project_writer import ProjectWriter
from ..prompt.documentation_builder import DocumentationPromptBuilder

logger = logging.getLogger(__name__)


class WriteDocumentationAction(BaseAction):
    """Action to generate and write a complete, production-ready README.md file to the project root."""

    name = "WriteDocumentation"
    description = "Generates a real, complete README.md file for the generated project."

    def __init__(
        self,
        prompt_builder: DocumentationPromptBuilder | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self.project_writer = project_writer or ProjectWriter()
        self.project_reader = project_reader or ProjectReader()
        self.artifact_manager = artifact_manager
        self.prompt_builder = prompt_builder or DocumentationPromptBuilder(self.project_reader, self.artifact_manager)
        super().__init__()

    def run(self, context: Any, llm: Any) -> ActionOutput:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        prompt_str = self.prompt_builder.build(context)
        system_prompt = getattr(self.prompt_builder, "SYSTEM_PROMPT", None) or "You are a Technical Writer generating a README.md file."

        content = llm.generate_text(
            prompt=prompt_str,
            system_prompt=system_prompt,
            max_tokens=3500,
        )
        if not isinstance(content, str):
            content = getattr(content, "content", str(content))

        # Strip code fences if present
        if content.startswith("```markdown"):
            content = content[len("```markdown") :].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()

        written = self.project_writer.write_file(
            project_id=project_id,
            file_path="README.md",
            content=content,
        )

        logger.info("Written README.md (%d chars) for project %s", len(content), project_id)

        structured = {
            "file_written": "README.md",
            "size_chars": len(content),
            "has_installation": "Getting Started" in content or "Installation" in content,
            "has_api_docs": "API" in content,
            "has_docker": "docker" in content.lower(),
        }

        return ActionOutput(
            content=content,
            structured=structured,
            tokens_used=0,
            latency_ms=0,
        )

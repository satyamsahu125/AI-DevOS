"""R6 — IntegrationDeveloperAgent.

Detects which external services an architecture requires, loads the
matching playbooks, and generates ready-to-use client code and
environment variable documentation for each service.

Runs as a release-phase stage (before QA) via WorkflowEngine.run().
Writes integration files to the project workspace so they appear in
the final download zip and in the VERIFICATION_REPORT.md.

Architecture principles followed:
- Stateless: all inputs come from context (memory / workspace) and
  all outputs go to workspace files + artifact.
- Single responsibility: only integrations; does not modify sprint code.
- Non-fatal: errors are logged and the pipeline continues.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..actions.base_action import BaseAction, ActionOutput
from ..llm.manager import LLMManager
from ..execution.project_writer import ProjectWriter
from ..execution.project_reader import ProjectReader
from ..shared.models.stage_artifact import StageArtifact
from .base_agent import BaseAgent
from ..integration import playbook_loader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt builder (inline — keeps the module self-contained)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an Integration Developer agent in an autonomous software engineering platform.

Your task: given an architecture description, identify which external services it needs and output
an integration plan. You must respond with valid JSON matching this exact schema:

{
  "detected_services": ["service1", "service2"],
  "integration_summary": "One sentence describing what integrations are needed.",
  "notes": "Any important notes about the integrations."
}

Rules:
- Only list services you are confident are actually needed based on the architecture.
- Omit services that are not clearly required.
- Use only these service names: stripe, jwt_auth, google_oauth, aws_s3, sendgrid, posthog
- If no external integrations are needed, return detected_services as an empty array.
"""

_USER_TEMPLATE = """Architecture and requirements context:

{context}

---

Identify which external services (from the playbook library) this project needs.
Return only JSON — no prose, no code fences.
"""


class _DetectIntegrationsAction(BaseAction):
    """LLM action that detects required services from architecture context."""

    name = "detect_integrations"
    description = "Detect external service integrations from architecture"

    def run(self, context: object, llm: object) -> ActionOutput:
        content = getattr(context, "content", "") if context is not None else ""
        project_id = getattr(context, "project_id", "") if context is not None else ""

        prompt = _USER_TEMPLATE.format(context=content[:8000])  # cap to avoid token overflow
        response = llm.generate_text(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            stage="integration",
            agent="integration_developer",
            project_id=project_id,
            json_mode=True,
        )
        raw = response.content if hasattr(response, "content") else str(response)
        structured = self.extract_json(raw)
        return ActionOutput(content=raw, structured=structured)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class IntegrationDeveloperAgent(BaseAgent):
    """Integration Developer: detects services from architecture and writes client code.

    Pipeline position: Release phase, before QA.

    On execute():
    1. Calls LLM to detect which services are needed (via _DetectIntegrationsAction).
    2. Loads playbooks for each detected service.
    3. Writes integration files to <workspace>/project/integrations/:
       - <service>_client.py / <service>_client.js — client boilerplate
       - INTEGRATIONS.md — env var documentation
    4. Returns ActionOutput with structured metadata for the artifact store.
    """

    artifact_name = "integration-output"

    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
    ) -> None:
        self._project_writer = project_writer or ProjectWriter()
        self._project_reader = project_reader or ProjectReader()
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        return _DetectIntegrationsAction()

    def execute(self, context: object) -> StageArtifact:
        """Override execute to chain detection → playbook loading → file writing."""
        # Step 1: detect services via LLM
        detection_artifact = super().execute(context)
        detected_services: list[str] = (detection_artifact.structured_content or {}).get("detected_services", [])

        # Fallback: if LLM detection failed or returned nothing, try keyword matching
        if not detected_services:
            content = getattr(context, "content", "") if context is not None else ""
            detected_services = playbook_loader.detect_from_text(content)
            logger.info(
                "[IntegrationDeveloperAgent] LLM detection empty — keyword fallback: %s",
                detected_services,
            )

        project_id = getattr(context, "project_id", "") if context is not None else ""
        logger.info(
            "[IntegrationDeveloperAgent] detected services: project=%s services=%s",
            project_id, detected_services,
        )

        # Step 2: load playbooks and write files
        integration_meta: list[dict[str, Any]] = []
        files_written: list[str] = []

        if detected_services and project_id:
            integration_dir = self._get_integration_dir(project_id)
            for service in detected_services:
                playbook = playbook_loader.get(service)
                if not playbook:
                    logger.warning("[IntegrationDeveloperAgent] no playbook for service: %s", service)
                    continue
                written = self._write_integration_files(integration_dir, service, playbook)
                files_written.extend(written)
                integration_meta.append({
                    "service": service,
                    "display_name": playbook.get("display_name", service),
                    "files_written": written,
                    "env_vars": [ev["name"] for ev in playbook.get("env_vars", [])],
                })

            # Write consolidated INTEGRATIONS.md
            md_path = self._write_integrations_md(integration_dir, detected_services)
            if md_path:
                files_written.append(md_path)

        # Step 3: return structured artifact
        structured = {
            "detected_services": detected_services,
            "integrations": integration_meta,
            "files_written": files_written,
            "integration_summary": (detection_artifact.structured_content or {}).get(
                "integration_summary", f"Integrated {len(detected_services)} service(s)."
            ),
        }
        summary = (
            f"Integration stage complete: {len(detected_services)} service(s) detected "
            f"({', '.join(detected_services) or 'none'}), "
            f"{len(files_written)} file(s) written."
        )
        return StageArtifact(
            artifact_id="",
            name=self.artifact_name,
            content=summary,
            status="Generated",
            schema_type="integration_output",
            structured_content=structured,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_integration_dir(self, project_id: str) -> Path:
        """Resolve the project's integrations directory, creating it if needed."""
        try:
            # WorkspaceManager is the canonical way to get the workspace path
            workspace_path = self._project_writer.workspace.get_workspace_path(project_id)
            project_dir = workspace_path / "project"
            integration_dir = project_dir / "integrations"
            integration_dir.mkdir(parents=True, exist_ok=True)
            return integration_dir
        except Exception as exc:
            logger.warning(
                "[IntegrationDeveloperAgent] could not resolve integration dir: project=%s error=%s",
                project_id, exc,
            )
            # Fallback to temp dir — files still get written, just not in workspace
            tmp = Path("/tmp") / f"devos_{project_id}_integrations"
            tmp.mkdir(parents=True, exist_ok=True)
            return tmp

    def _write_integration_files(
        self, integration_dir: Path, service: str, playbook: dict[str, Any]
    ) -> list[str]:
        """Write client code files for service from playbook. Returns list of written paths."""
        written: list[str] = []
        stack = self._detect_stack(integration_dir.parent)

        if stack == "python":
            snippet = playbook.get("python", {}).get("snippet", "")
            if snippet:
                file_path = integration_dir / f"{service}_client.py"
                header = (
                    f'"""Auto-generated integration client for {playbook.get("display_name", service)}.\n\n'
                    f'Docs: {playbook.get("docs_url", "")}\n\n'
                    f'Required env vars: {", ".join(ev["name"] for ev in playbook.get("env_vars", []))}\n"""\n\n'
                    f"import os\n\n"
                )
                file_path.write_text(header + snippet + "\n", encoding="utf-8")
                written.append(str(file_path.name))

        elif stack == "node":
            snippet = playbook.get("node", {}).get("snippet", "")
            if snippet:
                file_path = integration_dir / f"{service}_client.js"
                header = (
                    f"// Auto-generated integration client for {playbook.get('display_name', service)}\n"
                    f"// Docs: {playbook.get('docs_url', '')}\n"
                    f"// Required env vars: {', '.join(ev['name'] for ev in playbook.get('env_vars', []))}\n\n"
                    f"'use strict';\n\n"
                )
                file_path.write_text(header + snippet + "\n", encoding="utf-8")
                written.append(str(file_path.name))
        else:
            # Write both
            for lang, ext in [("python", "py"), ("node", "js")]:
                snippet = playbook.get(lang, {}).get("snippet", "")
                if snippet:
                    file_path = integration_dir / f"{service}_client.{ext}"
                    file_path.write_text(snippet + "\n", encoding="utf-8")
                    written.append(str(file_path.name))

        return written

    def _write_integrations_md(self, integration_dir: Path, services: list[str]) -> str | None:
        """Write INTEGRATIONS.md with env var documentation for all services."""
        if not services:
            return None
        lines: list[str] = [
            "# Required Integrations\n",
            "This file was auto-generated by the IntegrationDeveloperAgent (R6).\n",
            "Set these environment variables before running the application.\n\n",
        ]
        env_vars = playbook_loader.get_env_vars(services)
        if env_vars:
            lines.append("## Environment Variables\n\n")
            lines.append("| Variable | Service | Required | Description |\n")
            lines.append("|---|---|---|---|\n")
            for ev in env_vars:
                required = "✅" if ev.get("required") else "Optional"
                lines.append(f"| `{ev['name']}` | {ev.get('service', '')} | {required} | {ev.get('description', '')} |\n")
            lines.append("\n")
        for service in services:
            playbook = playbook_loader.get(service)
            if not playbook:
                continue
            lines.append(f"## {playbook.get('display_name', service)}\n\n")
            lines.append(f"{playbook.get('description', '')}\n\n")
            if playbook.get("docs_url"):
                lines.append(f"Docs: {playbook['docs_url']}\n\n")
            evs = playbook.get("env_vars", [])
            if evs:
                lines.append("**Required environment variables:**\n\n")
                for ev in evs:
                    req = " *(required)*" if ev.get("required") else " *(optional)*"
                    lines.append(f"- `{ev['name']}`{req}: {ev.get('description', '')}\n")
                lines.append("\n")

        md_path = integration_dir / "INTEGRATIONS.md"
        md_path.write_text("".join(lines), encoding="utf-8")
        return "INTEGRATIONS.md"

    def _detect_stack(self, project_dir: Path) -> str:
        """Detect project stack from file system — returns 'python', 'node', or 'unknown'."""
        if not project_dir.exists():
            return "unknown"
        if any(project_dir.rglob("requirements.txt")):
            return "python"
        if any(project_dir.rglob("package.json")):
            return "node"
        # Check for common language files
        if any(project_dir.rglob("*.py")):
            return "python"
        if any(project_dir.rglob("*.js")) or any(project_dir.rglob("*.ts")):
            return "node"
        return "unknown"

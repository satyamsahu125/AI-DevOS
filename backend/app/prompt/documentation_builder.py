from __future__ import annotations

import logging
from typing import Any
from .builder import PromptBuilder
from ..artifact.manager import ArtifactManager
from ..execution.project_reader import ProjectReader

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Technical Writer for software projects.
You write README files that developers can actually follow.

YOUR ONLY OUTPUT: A single, complete README.md file.
No extra conversational text. Just the markdown content.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
README STRUCTURE (always include ALL sections)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# {Project Name}

> One-line description of what this project does.

## Features
  Bullet list of actual features (from requirements artifact).
  Not generic — specific to this project.

## Tech Stack
  - Backend: Python + FastAPI
  - Database: PostgreSQL + SQLAlchemy
  - Frontend: React / Next.js + TypeScript + Tailwind CSS

## Prerequisites
  List exact tools needed:
  - Python 3.11+
  - Node.js 20+ (if frontend exists)
  - Docker + Docker Compose

## Getting Started

### Option 1: Docker (Recommended)
  git clone {repo_url}
  cd {project_name}
  cp .env.example .env
  docker-compose up --build
  
  Backend: http://localhost:8000
  API Docs: http://localhost:8000/docs
  Frontend: http://localhost:3000

### Option 2: Local Development
  # Backend
  cd backend
  python -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  cp ../.env.example ../.env
  uvicorn main:app --reload

## Environment Variables
  Table of all env vars with descriptions:
  | Variable | Required | Description | Example |
  |----------|----------|-------------|---------|

## API Documentation
  Auto-generated docs available at:
  - Swagger UI: http://localhost:8000/docs
  - ReDoc: http://localhost:8000/redoc
  
  Key endpoints:
  | Method | Path | Description | Auth |
  |--------|------|-------------|------|

## Running Tests
  cd {project_root}
  pip install pytest pytest-asyncio httpx
  pytest tests/ -v

## Project Structure
  Show actual file tree.

## Contributing
  Standard contribution steps.

## License
  MIT License

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Use ACTUAL project name from project metadata
2. List ACTUAL features from requirements artifact
3. Use ACTUAL tech stack detected from files
4. Show ACTUAL API routes in endpoint table
5. Reference ACTUAL environment variables from .env.example
6. Show ACTUAL file tree (main files)
7. All commands must be runnable as-is
"""


class DocumentationPromptBuilder(PromptBuilder):
    """Prompt builder for complete README.md documentation generation."""

    def __init__(
        self,
        project_reader: ProjectReader | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        super().__init__(role="Documentation")
        self.project_reader = project_reader or ProjectReader()
        self.artifact_manager = artifact_manager

    def build(self, context: Any | None = None) -> str:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        files = self.project_reader.list_all_files(project_id) if project_id else []
        routes = self.project_reader.get_api_routes(project_id) if project_id else []
        stack = self.project_reader.get_tech_stack(project_id) if project_id else {}
        requirements_txt = (self.project_reader.get_requirements_txt(project_id) or "") if project_id else ""
        env_example = (self.project_reader.read_file(project_id, ".env.example") or "") if project_id else ""

        routes_table = "\n".join([f"  {r['method']} {r['path']} — {r['function']}" for r in routes]) or "  List main endpoints"

        features_text = ""
        if self.artifact_manager and project_id:
            try:
                requirements_artifact = self.artifact_manager.get_artifact(project_id, "product_owner")
                if requirements_artifact and hasattr(requirements_artifact, "structured"):
                    goals = getattr(requirements_artifact.structured, "goals", []) or []
                    if isinstance(goals, list):
                        features_text = "\n".join(f"  - {g}" for g in goals[:8])
            except Exception as e:
                logger.warning(
                    "[DocumentationPromptBuilder.build] Non-critical failure reading requirements artifact: %s",
                    str(e),
                    exc_info=True,
                )

        project_name = getattr(context, "project_name", "AI Application") if context else "AI Application"
        original_request = getattr(context, "content", "") or getattr(context, "original_request", "") or (context if isinstance(context, str) else "Generated Application")

        user_prompt = f"""
Write a complete README.md for this project.

PROJECT: {project_name}
DESCRIPTION: {original_request}

TECH STACK:
  Backend entry: {stack.get('backend_entry', 'backend/main.py')}
  Has frontend: {stack.get('has_react', False)}
  Uses PostgreSQL: {stack.get('uses_sqlalchemy', False)}
  Backend port: {stack.get('backend_port', 8000)}
  Frontend port: {stack.get('frontend_port', 3000)}

KEY FEATURES:
{features_text or "  Infer from project description"}

API ROUTES:
{routes_table}

REQUIREMENTS.TXT:
{requirements_txt[:400] or "  Not found"}

.ENV.EXAMPLE:
{env_example[:400] or "  Not found"}

ALL PROJECT FILES:
{chr(10).join(f'  {f}' for f in files)}

Write a complete, professional README.md with all 11 required sections.
Every command must work when followed step by step.
"""
        return f"{SYSTEM_PROMPT}\n\n{user_prompt}"

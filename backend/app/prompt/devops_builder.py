from __future__ import annotations

from typing import Any
from .builder import PromptBuilder
from ..execution.project_reader import ProjectReader

SYSTEM_PROMPT = """You are a Senior DevOps Engineer and SRE.
You write production-ready Docker and CI/CD configurations.

YOUR ONLY OUTPUT: Complete, real configuration files.
No explanations. No markdown prose. Just file content in file blocks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES YOU ALWAYS PRODUCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: Dockerfile
  Multi-stage build for the backend.
  Template for Python/FastAPI:
  
  FROM python:3.11-slim AS builder
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir --user -r requirements.txt
  
  FROM python:3.11-slim AS runtime
  WORKDIR /app
  COPY --from=builder /root/.local /root/.local
  COPY . .
  ENV PATH=/root/.local/bin:$PATH
  ENV PYTHONDONTWRITEBYTECODE=1
  ENV PYTHONUNBUFFERED=1
  EXPOSE 8000
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FILE 2: docker-compose.yml
  Full local development stack.
  Always includes: backend, database (postgres), and frontend (if exists).
  
  version: '3.9'
  services:
    backend:
      build:
        context: ./backend
        dockerfile: ../Dockerfile
      ports:
        - "8000:8000"
      environment:
        DATABASE_URL: postgresql://devos:devos@db:5432/devos
        SECRET_KEY: dev-secret-key-change-in-production
      depends_on:
        db:
          condition: service_healthy
      volumes:
        - ./backend:/app
      restart: unless-stopped
    
    db:
      image: postgres:15-alpine
      environment:
        POSTGRES_USER: devos
        POSTGRES_PASSWORD: devos
        POSTGRES_DB: devos
      volumes:
        - postgres_data:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U devos"]
        interval: 10s
        timeout: 5s
        retries: 5
  
  volumes:
    postgres_data:

FILE 3: .env.example
  Template for all required environment variables.
  NEVER include real secrets — only variable names + descriptions.

FILE 4: .github/workflows/ci.yml
  GitHub Actions CI pipeline.

Output format:
===FILE: Dockerfile===
[content]
===END===

===FILE: docker-compose.yml===
[content]
===END===

===FILE: .env.example===
[content]
===END===

===FILE: .github/workflows/ci.yml===
[content]
===END===
"""


class DevOpsPromptBuilder(PromptBuilder):
    """Prompt builder for DevOps generation."""

    def __init__(self, project_reader: ProjectReader | None = None) -> None:
        super().__init__(role="DevOps")
        self.project_reader = project_reader or ProjectReader()

    def build(self, context: Any | None = None) -> str:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        stack = self.project_reader.get_tech_stack(project_id) if project_id else {}
        files = self.project_reader.list_all_files(project_id) if project_id else []
        requirements = (self.project_reader.get_requirements_txt(project_id) or "") if project_id else ""
        config_content = (self.project_reader.read_file(project_id, "backend/config.py") or "") if project_id else ""
        main_entry = stack.get("backend_entry", "backend/main.py") if stack else "backend/main.py"
        main_content = ((self.project_reader.read_file(project_id, main_entry) or "")[:1000]) if project_id else ""

        user_prompt = f"""
Write complete DevOps configuration files for this project.

DETECTED TECH STACK:
  Backend: {stack.get('backend_language', 'python')}
  Entry point: {main_entry}
  Has React frontend: {stack.get('has_react', False)}
  Uses SQLAlchemy: {stack.get('uses_sqlalchemy', False)}
  Uses Alembic: {stack.get('uses_alembic', False)}
  Uses Redis: {stack.get('uses_redis', False)}
  Backend port: {stack.get('backend_port', 8000)}
  Frontend port: {stack.get('frontend_port', 3000)}

REQUIREMENTS.TXT CONTENT:
{requirements[:500] or "Not found — infer from imports in code"}

CONFIG.PY (for env vars):
{config_content[:800] or "Not found"}

MAIN.PY ENTRY POINT:
{main_content}

ALL PROJECT FILES:
{chr(10).join(files)}

Write Dockerfile, docker-compose.yml, .env.example, and .github/workflows/ci.yml.
Match actual entry point and dependencies found above.
Include postgres service if SQLAlchemy is detected.
Include redis service only if Redis is detected.
"""
        return f"{SYSTEM_PROMPT}\n\n{user_prompt}"

from __future__ import annotations

from typing import Any
from .builder import PromptBuilder
from ..execution.project_reader import ProjectReader

_WEB_DEVOPS_PROMPT = """You are a Senior DevOps Engineer and SRE.
You write production-ready Docker and CI/CD configurations.

YOUR ONLY OUTPUT: Complete, real configuration files.
No explanations. No markdown prose. Just file content in file blocks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES YOU ALWAYS PRODUCE (WEB PROJECT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: Dockerfile — Multi-stage build for the backend.
FILE 2: docker-compose.yml — Full local development stack.
FILE 3: .dockerignore — Exclude __pycache__, .venv, .env, .git, node_modules
FILE 4: .env.example — Template env vars (no real secrets)
FILE 5: .github/workflows/ci.yml — GitHub Actions CI pipeline

Output format:
===FILE: Dockerfile===
[content]
===END===

===FILE: docker-compose.yml===
[content]
===END===

===FILE: .dockerignore===
[content]
===END===

===FILE: .env.example===
[content]
===END===

===FILE: .github/workflows/ci.yml===
[content]
===END===
"""

_MOBILE_DEVOPS_PROMPT = """You are a Senior Mobile DevOps Engineer specialising in Expo / React Native.
You write production-ready Expo configuration and CI/CD for mobile apps.

YOUR ONLY OUTPUT: Complete, real configuration files.
No explanations. No markdown prose. Just file content in file blocks.
Do NOT write Dockerfile or docker-compose — mobile apps are not containerised.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES YOU ALWAYS PRODUCE (MOBILE / EXPO PROJECT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: app.json
  Expo app configuration. YOU MUST USE EXACTLY SDK 51 — no newer version.
  Include:
    name, slug, version: "1.0.0", orientation: "portrait",
    sdkVersion: "51.0.0",  ← REQUIRED EXACTLY THIS VALUE
    icon: "./assets/icon.png", splash.image: "./assets/splash.png",
    platforms: ["ios", "android"],
    ios.bundleIdentifier, android.package, permissions

FILE 2: eas.json
  Expo Application Services build profiles:
    development: { developmentClient: true, distribution: "internal" }
    preview:     { distribution: "internal" }
    production:  { distribution: "store" }

FILE 3: babel.config.js
  Expo preset (SDK 51 compatible):
    module.exports = function(api) {
      api.cache(true);
      return { presets: ['babel-preset-expo'] };
    };

FILE 4: metro.config.js
  Metro bundler config (SDK 51):
    const { getDefaultConfig } = require('expo/metro-config');
    module.exports = getDefaultConfig(__dirname);

FILE 5: .github/workflows/ci.yml
  GitHub Actions using expo-github-action:
    - actions/checkout
    - actions/setup-node (node 20)
    - expo/expo-github-action@v8 (with Expo token)
    - npm ci
    - npx expo install --check
    - npx jest --ci

CRITICAL SDK PINNING RULE:
  In app.json:   "sdkVersion": "51.0.0"
  In package.json dependencies (if you write one): "expo": "~51.0.0"
  Never use SDK 52, 53, or higher — Expo Go only supports SDK 51 (current stable).
  Users on SDK 52+ see "Project is incompatible with this version of Expo Go" error.

Output format:
===FILE: app.json===
[content]
===END===

===FILE: eas.json===
[content]
===END===

===FILE: babel.config.js===
[content]
===END===

===FILE: metro.config.js===
[content]
===END===

===FILE: .github/workflows/ci.yml===
[content]
===END===
"""

# Backward-compat alias
SYSTEM_PROMPT = _WEB_DEVOPS_PROMPT


class DevOpsPromptBuilder(PromptBuilder):
    """Prompt builder for DevOps generation.

    Switches between Docker-based config (web) and Expo/EAS config (mobile)
    depending on the project's tech stack detected from generated files.
    """

    def __init__(self, project_reader: ProjectReader | None = None) -> None:
        super().__init__(role="DevOps")
        self.project_reader = project_reader or ProjectReader()

    @staticmethod
    def _is_mobile_project(files: list[str], stack: dict) -> bool:
        mobile_signals = {"app.json", "metro.config.js", "babel.config.js", "eas.json"}
        if any(f in mobile_signals for f in files):
            return True
        if stack.get("is_mobile"):
            return True
        has_backend = any(f.startswith("backend/") for f in files)
        has_rn = any("react-native" in f or "expo" in f.lower() for f in files)
        return has_rn and not has_backend

    def build(self, context: Any | None = None) -> str:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        stack = self.project_reader.get_tech_stack(project_id) if project_id else {}
        files = self.project_reader.list_all_files(project_id) if project_id else []
        project_type = stack.get("project_type", "web_fullstack")

        if project_type == "mobile_app" or self._is_mobile_project(files, stack):
            return self._build_mobile_prompt(files)
        if project_type == "ml_pipeline":
            return self._build_ml_prompt(files, stack)
        return self._build_web_prompt(project_id, stack, files)

    def _build_ml_prompt(self, files: list[str], stack: dict) -> str:
        ml_system = """You are a Senior MLOps Engineer.
You write production-ready requirements.txt and CI/CD for Python ML pipelines.

YOUR ONLY OUTPUT: Complete configuration files inside file blocks.
No Docker-compose with postgres. No React. No web server (unless serving is needed).

FILES YOU PRODUCE:
  requirements.txt     — all Python deps pinned to minor versions
  .github/workflows/ci.yml — CI that installs deps + runs pytest (fast, synthetic data)
  Optional: Dockerfile  — only if an inference API server was requested
  Optional: .env.example — only if env vars are needed (API keys, paths)

CI template:
  name: ML Pipeline CI
  on: [push, pull_request]
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: '3.11' }
        - run: pip install -r requirements.txt
        - run: pytest tests/ -v --tb=short

requirements.txt example (PyTorch project):
  torch==2.2.*
  numpy==1.26.*
  pandas==2.2.*
  scikit-learn==1.4.*
  pytest==8.1.*
  mlflow==2.12.*   # only if tracking is used

Output format:
===FILE: requirements.txt===
[content]
===END===

===FILE: .github/workflows/ci.yml===
[content]
===END===
"""
        reqs = self.project_reader.get_requirements_txt("") or ""
        user_prompt = f"""
Write DevOps configuration for this Python ML pipeline.

DETECTED STACK:
  project_type: ml_pipeline
  ML framework: {stack.get('backend_language', 'python')}

EXISTING requirements.txt:
{reqs[:800] or "Not found — infer from project files"}

ALL PROJECT FILES:
{chr(10).join(files)}

Write requirements.txt and .github/workflows/ci.yml.
Only add a Dockerfile if train.py or api/main.py needs to run in a container.
"""
        return f"{ml_system}\n\n{user_prompt}"

    def _build_mobile_prompt(self, files: list[str]) -> str:
        user_prompt = f"""
Write complete Expo/EAS configuration files for this React Native mobile app.

PROJECT FILES:
  {chr(10).join(files)}

Write app.json, eas.json, babel.config.js, metro.config.js, and .github/workflows/ci.yml.
Use expo-github-action in CI. Do NOT write Dockerfile or docker-compose.
"""
        return f"{_MOBILE_DEVOPS_PROMPT}\n\n{user_prompt}"

    def _build_web_prompt(self, project_id: str, stack: dict, files: list[str]) -> str:
        requirements = (self.project_reader.get_requirements_txt(project_id) or "") if project_id else ""
        config_content = (self.project_reader.read_file(project_id, "backend/config.py") or "") if project_id else ""
        main_entry = stack.get("backend_entry", "backend/main.py")
        main_content = ((self.project_reader.read_file(project_id, main_entry) or "")[:1000]) if project_id else ""

        user_prompt = f"""
Write complete DevOps configuration files for this web project.

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
        return f"{_WEB_DEVOPS_PROMPT}\n\n{user_prompt}"

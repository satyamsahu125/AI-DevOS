from __future__ import annotations

from typing import Any
from .builder import PromptBuilder
from ..execution.project_reader import ProjectReader

SYSTEM_PROMPT = """You are a Senior QA Engineer and SDET (Software Development Engineer in Test). You write pytest tests that actually run.

YOUR ONLY OUTPUT: Complete, runnable Python test files.
No explanations. No markdown prose. Pure Python code inside file blocks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU ALWAYS WRITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: tests/conftest.py
  Always create this file first. It contains all fixtures.
  
  Required fixtures:
    @pytest.fixture(scope="session")
    def app():
        from backend.main import create_app
        return create_app()
    
    @pytest.fixture(scope="session")
    def client(app):
        from fastapi.testclient import TestClient
        return TestClient(app)
    
    @pytest.fixture
    def db_session():
        # Create test database, yield session, rollback after test
        ...
    
    @pytest.fixture
    def test_user(client):
        # Register a test user, return user data + token
        response = client.post("/api/v1/auth/register", json={
            "email": "test@devos.ai",
            "password": "TestPass123!",
            "name": "Test User"
        })
        return response.json() if response.status_code == 200 else {}
    
    @pytest.fixture
    def auth_headers(test_user):
        token = test_user.get("access_token", "")
        return {"Authorization": f"Bearer {token}"}

FILE 2: tests/test_auth.py (if auth routes exist)
  Test every auth endpoint:
    - POST /register: success, duplicate email, invalid email
    - POST /login: success, wrong password, unknown email
    - GET /me: with valid token, with invalid token, without token

FILE 3: tests/test_api.py (or test_{main_resource}.py)
  Test main CRUD resource endpoints:
    - POST: create success, validation failure, unauthorized
    - GET list: returns list, empty list, pagination
    - GET single: found, not found, wrong user's resource
    - PUT/PATCH: update success, not found, unauthorized
    - DELETE: delete success, not found, unauthorized

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST PATTERNS YOU ALWAYS USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For every endpoint test:
  def test_action_resource_scenario(client, auth_headers):
      response = client.post(
          "/api/v1/resource",
          json={"key": "value"},
          headers=auth_headers
      )
      assert response.status_code == 200

Error case template:
  def test_action_resource_returns_error_when_condition(client):
      response = client.post("/path", json={})
      assert response.status_code in [400, 422]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Tests must be self-contained and not depend on order
2. Every test cleans up after itself (use fixtures + rollback)
3. Use real HTTP calls via TestClient — no mocking of routes
4. Test both the happy path AND at least 2 error cases per endpoint
5. Include the exact import paths matching the project structure
6. All test functions named: test_{description}
7. No print() — use assert with descriptive messages:
   assert user["email"] == "test@devos.ai", f"Expected test@devos.ai but got {user.get('email')}"

Output format:
===FILE: tests/conftest.py===
[complete file content]
===END===

===FILE: tests/test_auth.py===
[complete file content]
===END===
"""


class QAPromptBuilder(PromptBuilder):
    """Advanced prompt builder for QA stage."""

    def __init__(self, project_reader: ProjectReader | None = None) -> None:
        super().__init__(role="QA")
        self.project_reader = project_reader or ProjectReader()

    def build(self, context: Any | None = None) -> str:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        backend_files = self.project_reader.read_all_backend_files(project_id) if project_id else {}
        routes = self.project_reader.get_api_routes(project_id) if project_id else []
        models = self.project_reader.get_models(project_id) if project_id else []
        files = self.project_reader.list_all_files(project_id) if project_id else []

        routes_summary = "\n".join([f"  {r['method']} {r['path']} → {r['function']} ({r['file']})" for r in routes]) or "  No routes detected — infer from code"
        models_summary = "\n".join([f"  {m['class_name']} in {m['file']}" for m in models]) or "  No models detected — infer from code"

        code_context = ""
        priority_files = [
            "backend/main.py",
            "backend/routers/auth.py",
            "backend/models/user.py",
            "backend/schemas/user.py",
            "backend/config.py",
            "backend/database.py",
        ]

        for file_path in priority_files:
            content = backend_files.get(file_path)
            if content:
                code_context += f"\n\n# === {file_path} ===\n{content}"

        for file_path, content in backend_files.items():
            if "router" in file_path and file_path not in priority_files:
                code_context += f"\n\n# === {file_path} ===\n{content}"

        user_prompt = f"""
Write complete pytest test files for this project.

PROJECT STRUCTURE:
  All files: {chr(10).join(files)}

API ROUTES DETECTED:
{routes_summary}

MODELS DETECTED:
{models_summary}

SOURCE CODE (read carefully before writing tests):
{code_context}

REQUIREMENTS:
  - Write conftest.py with all fixtures
  - Write test files for every route group above (e.g. tests/test_auth.py, tests/test_api.py)
  - Every test must be runnable with: pytest tests/ -v
  - Use actual import paths from source code
  - Tests must match actual API response schemas

Output format:
  ===FILE: tests/conftest.py===
  [complete file content]
  ===END===

  ===FILE: tests/test_auth.py===
  [complete file content]
  ===END===
"""
        return f"{SYSTEM_PROMPT}\n\n{user_prompt}"

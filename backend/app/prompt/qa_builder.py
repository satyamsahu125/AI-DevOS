from __future__ import annotations

from typing import Any
from .builder import PromptBuilder
from ..execution.project_reader import ProjectReader

_WEB_SYSTEM_PROMPT = """You are a Senior QA Engineer and SDET (Software Development Engineer in Test). You write pytest tests that actually run.

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
        from {app_module} import {app_factory}
        return {app_factory}()

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
        response = client.post("{auth_endpoint}", json={{
            "email": "test@devos.ai",
            "password": "TestPass123!",
            "name": "Test User"
        }})
        return response.json() if response.status_code == 200 else {{}}

    @pytest.fixture
    def auth_headers(test_user):
        token = test_user.get("access_token", "")
        return {{"Authorization": f"Bearer {{token}}"}}

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

CRITICAL RULE: You are a QA Engineer, not a validator. Your primary goal is to find bugs. You MUST write tests for edge cases and negative paths. This includes testing for: invalid file types, empty inputs, file permission errors, and incorrect API responses.

CRITICAL RULE: Do NOT over-mock. Mocking should be used sparingly. You should NOT mock the core logic of the function being tested. Test the actual file I/O and data processing where possible, only mocking external network endpoints.

Output format:
===FILE: tests/conftest.py===
[complete file content]
===END===

===FILE: tests/test_auth.py===
[complete file content]
===END===
"""

_MOBILE_SYSTEM_PROMPT = """You are a Senior QA Engineer and SDET specialising in React Native / Expo applications.

YOUR ONLY OUTPUT: Complete, runnable TypeScript/Jest test files.
No explanations. No markdown prose. Pure TypeScript inside file blocks.
Do NOT write Python or pytest — this is a mobile app with no backend server.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TESTING FRAMEWORK: Jest + @testing-library/react-native
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: __tests__/[ServiceName].test.ts
  Unit tests for the core business logic / services:
    - Core functions: test happy path, edge cases, error handling
    - Pure utility functions: test all exported functions
    - State management: test actions, reducers, selectors

FILE 2: __tests__/[ScreenName].test.tsx
  Component integration test using @testing-library/react-native:
    - Renders UI elements correctly
    - User interactions update state/display
    - Error states show correct messages
    - Navigation works as expected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PATTERNS TO USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Unit test (logic):
  import { yourFunction } from '../src/services/yourService';
  describe('yourFunction', () => {
    it('handles normal input', () => {
      expect(yourFunction(validInput)).toBe(expectedOutput);
    });
    it('throws on invalid input', () => {
      expect(() => yourFunction(invalidInput)).toThrow('Expected error');
    });
  });

Component test:
  import { render, fireEvent } from '@testing-library/react-native';
  import YourScreen from '../src/screens/YourScreen';
  it('renders correctly', () => {
    const { getByText, getByTestId } = render(<YourScreen />);
    expect(getByText('Expected Text')).toBeTruthy();
  });

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ONLY write tests for features that ACTUALLY EXIST in the source code files
2. Import from the exact file paths found in the project
3. Never import FastAPI, pytest, httpx, or any Python library
4. Test both happy path and at least 2 error cases per function
5. All describe blocks named after the module being tested
6. AsyncStorage mock: jest.mock('@react-native-async-storage/async-storage', ...)

Output format:
===FILE: __tests__/[ServiceName].test.ts===
[complete file content]
===END===

===FILE: __tests__/[ScreenName].test.tsx===
[complete file content]
===END===
"""

# Keep backward-compat alias used by write_qa_report.py
SYSTEM_PROMPT = _WEB_SYSTEM_PROMPT


class QAPromptBuilder(PromptBuilder):
    """Advanced prompt builder for QA stage.

    Detects mobile projects (React Native / Expo) from the generated file tree
    and switches to Jest + @testing-library/react-native instead of pytest.
    """

    def __init__(self, project_reader: ProjectReader | None = None) -> None:
        super().__init__(role="QA")
        self.project_reader = project_reader or ProjectReader()

    def build(self, context: Any | None = None) -> str:
        project_id = getattr(context, "project_id", "") or (context if isinstance(context, str) else "")

        files = self.project_reader.list_all_files(project_id) if project_id else []
        stack = self.project_reader.get_tech_stack(project_id) if project_id else {}
        project_type = stack.get("project_type", "web_fullstack")

        if project_type == "mobile_app" or stack.get("is_mobile"):
            return self._build_mobile_prompt(project_id, files)
        if project_type == "ml_pipeline":
            return self._build_ml_prompt(project_id, files)
        if project_type == "cli_tool":
            return self._build_cli_prompt(project_id, files)
        return self._build_web_prompt(project_id, files)

    # Per-builder char budgets — keeps total prompt comfortably below the
    # 600 000-char pre-flight trim in StageRunner and the 262 144-token Bedrock
    # limit.  Actual limits:
    #   file-list  : 8 000 chars  (~200 source-file paths, well above typical)
    #   code-ctx   : 40 000 chars (~11 000 tokens — plenty for QA context)
    #   per-file   : 3 000 chars  (read_all_backend_files already truncates at
    #                               2 000, so this is a belt-and-suspenders cap)
    _MAX_FILE_LIST_CHARS: int = 8_000
    _MAX_CODE_CTX_CHARS: int = 40_000
    _MAX_PER_FILE_CHARS: int = 3_000

    def _build_mobile_prompt(self, project_id: str, files: list[str]) -> str:
        """Jest + @testing-library/react-native for React Native / Expo projects."""
        source_files = self.project_reader.read_all_backend_files(project_id) if project_id else {}

        # Cap total code context to avoid context-window overflow.
        # list_all_files() already excludes node_modules, but the source files
        # themselves can still be large for multi-sprint projects.
        # Include all relevant source files (screens, services, hooks, utils, etc.)
        # without hardcoded calculator/math keywords.
        code_context = ""
        relevant_keywords = ("parser", "memory", "utils", "hooks", "screen", "service", "api", "store", "component", "navigation", "context", "provider")
        for file_path, content in source_files.items():
            if not any(k in file_path.lower() for k in relevant_keywords):
                continue
            snippet = content[:self._MAX_PER_FILE_CHARS]
            if len(content) > self._MAX_PER_FILE_CHARS:
                snippet += "\n// ... [truncated for context]"
            addition = f"\n\n// === {file_path} ===\n{snippet}"
            if len(code_context) + len(addition) > self._MAX_CODE_CTX_CHARS:
                break
            code_context += addition

        # Likewise cap the file list so a project with hundreds of config /
        # lock files does not bloat the prompt.
        files_text = chr(10).join(files)
        if len(files_text) > self._MAX_FILE_LIST_CHARS:
            files_text = files_text[:self._MAX_FILE_LIST_CHARS] + "\n  ... [list truncated]"

        user_prompt = f"""
Write complete Jest test files for this React Native / Expo mobile app.

PROJECT FILES:
  {files_text}

SOURCE CODE (read carefully — only test what actually exists):
{code_context or "  No source files found — write tests based on the project structure above."}

REQUIREMENTS:
  - Write TypeScript test files using Jest + @testing-library/react-native
  - Test core business logic / services with unit tests
  - Test UI components / screens with integration tests
  - Import from exact file paths found in the project
  - Do NOT write Python, pytest, conftest.py, or any FastAPI code

Output format:
  ===FILE: __tests__/[ServiceName].test.ts===
  [complete file content]
  ===END===

  ===FILE: __tests__/[ScreenName].test.tsx===
  [complete file content]
  ===END===
"""
        # Return only the user prompt; the system prompt (_MOBILE_SYSTEM_PROMPT)
        # should be passed separately to generate_text() by the caller.
        return user_prompt

    def _build_ml_prompt(self, project_id: str, files: list[str]) -> str:
        """pytest tests for ML pipeline projects — tests math, not HTTP endpoints."""
        ml_system = """You are a Senior ML Engineer and QA specialist.
You write pytest tests for Python ML pipelines (model correctness, data loading, training).

YOUR ONLY OUTPUT: Complete, runnable Python test files.
No explanations. No markdown prose. Pure Python inside file blocks.
Do NOT test HTTP endpoints unless an inference API is explicitly present.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU WRITE FOR A ML PIPELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE 1: tests/test_model.py
  Test model architecture:
    - Model instantiates without error
    - Forward pass produces correct output shape
    - Output is finite (no NaN / Inf)
    - Parameter count is reasonable

FILE 2: tests/test_data.py
  Test data loading and preprocessing:
    - Dataset loads without error
    - Sample has correct shape/dtype
    - Labels are within valid range
    - Transforms produce expected output

FILE 3: tests/test_training.py (smoke test — fast, tiny data)
  Test training loop:
    - Loss decreases after 5 steps on 10 synthetic samples
    - Checkpoint saving / loading round-trips correctly
    - Training completes without error

FILE 4: tests/test_inference.py
  Test inference / predict:
    - predict() accepts valid input and returns expected shape
    - predict() raises ValueError on invalid input shape
    - Batch inference matches single-sample inference

Test patterns:
  import torch
  def test_model_output_shape():
      model = LSTMModel(input_size=10, hidden_size=64, output_size=1)
      x = torch.randn(32, 10, 10)  # (batch, seq_len, features)
      out = model(x)
      assert out.shape == (32, 1), f"Expected (32,1) got {out.shape}"

  def test_loss_decreases():
      model = LSTMModel(...)
      opt = torch.optim.Adam(model.parameters())
      losses = []
      for _ in range(5):
          loss = train_step(model, opt, synthetic_batch())
          losses.append(loss)
      assert losses[-1] < losses[0], "Loss did not decrease"

Output format:
===FILE: tests/test_model.py===
[content]
===END===
"""
        source_files = self.project_reader.read_all_backend_files(project_id) if project_id else {}
        code_ctx = ""
        for fp, content in source_files.items():
            if not any(k in fp for k in ("model", "dataset", "train", "config", "utils")):
                continue
            snippet = content[:self._MAX_PER_FILE_CHARS]
            if len(content) > self._MAX_PER_FILE_CHARS:
                snippet += "\n# ... [truncated]"
            addition = f"\n\n# === {fp} ===\n{snippet}"
            if len(code_ctx) + len(addition) > self._MAX_CODE_CTX_CHARS:
                break
            code_ctx += addition

        files_text = chr(10).join(files)
        if len(files_text) > self._MAX_FILE_LIST_CHARS:
            files_text = files_text[:self._MAX_FILE_LIST_CHARS] + "\n  ... [list truncated]"

        user_prompt = f"""
Write complete pytest test files for this ML pipeline.

PROJECT FILES:
  {files_text}

SOURCE CODE (read imports and class/function signatures carefully):
{code_ctx or "  Source files not found — write tests based on project structure above."}

REQUIREMENTS:
  - Test model correctness, data loading, training loop, inference
  - Use synthetic/random data so tests run fast (no real dataset needed)
  - Tests must pass with: pytest tests/ -v
  - Import from actual file paths found above
  - Never import FastAPI, TestClient, or web libraries
"""
        return f"{ml_system}\n\n{user_prompt}"

    def _build_cli_prompt(self, project_id: str, files: list[str]) -> str:
        """pytest tests for CLI tools using Click/Typer test runners."""
        cli_system = """You are a Senior QA Engineer writing tests for CLI applications.

YOUR ONLY OUTPUT: Complete, runnable Python test files.
Use Click's testing.CliRunner or Typer's testing.CliRunner — not HTTP clients.

Test patterns:
  from click.testing import CliRunner
  from cli.main import cli

  def test_help_command():
      runner = CliRunner()
      result = runner.invoke(cli, ['--help'])
      assert result.exit_code == 0
      assert 'Usage' in result.output

  def test_subcommand_success():
      runner = CliRunner()
      result = runner.invoke(cli, ['run', '--input', 'file.csv'])
      assert result.exit_code == 0

  def test_subcommand_missing_arg():
      runner = CliRunner()
      result = runner.invoke(cli, ['run'])
      assert result.exit_code != 0

Output format:
===FILE: tests/test_cli.py===
[content]
===END===
"""
        source_files = self.project_reader.read_all_backend_files(project_id) if project_id else {}
        code_ctx = ""
        for fp, c in source_files.items():
            if not any(k in fp for k in ("cli", "command", "main")):
                continue
            snippet = c[:self._MAX_PER_FILE_CHARS]
            addition = f"\n\n# === {fp} ===\n{snippet}"
            if len(code_ctx) + len(addition) > self._MAX_CODE_CTX_CHARS:
                break
            code_ctx += addition

        files_text = chr(10).join(files)
        if len(files_text) > self._MAX_FILE_LIST_CHARS:
            files_text = files_text[:self._MAX_FILE_LIST_CHARS] + "\n  ... [list truncated]"

        user_prompt = f"""
Write complete pytest test files for this CLI tool.

PROJECT FILES:
  {files_text}

SOURCE CODE:
{code_ctx or "  Source files not found — write tests based on project structure above."}

REQUIREMENTS:
  - Use Click/Typer CliRunner, not HTTP clients
  - Test every command group: help, main commands, error cases
  - Tests must pass with: pytest tests/ -v
"""
        return f"{cli_system}\n\n{user_prompt}"

    def _build_web_prompt(self, project_id: str, files: list[str]) -> str:
        """pytest + FastAPI TestClient for web projects."""
        backend_files = self.project_reader.read_all_backend_files(project_id) if project_id else {}
        routes = self.project_reader.get_api_routes(project_id) if project_id else []
        models = self.project_reader.get_models(project_id) if project_id else []

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
            if content and len(code_context) < self._MAX_CODE_CTX_CHARS:
                snippet = content[:self._MAX_PER_FILE_CHARS]
                code_context += f"\n\n# === {file_path} ===\n{snippet}"
        for file_path, content in backend_files.items():
            if "router" in file_path and file_path not in priority_files:
                if len(code_context) >= self._MAX_CODE_CTX_CHARS:
                    break
                snippet = content[:self._MAX_PER_FILE_CHARS]
                code_context += f"\n\n# === {file_path} ===\n{snippet}"

        files_text = chr(10).join(files)
        if len(files_text) > self._MAX_FILE_LIST_CHARS:
            files_text = files_text[:self._MAX_FILE_LIST_CHARS] + "\n  ... [list truncated]"

        user_prompt = f"""
Write complete pytest test files for this web project.

PROJECT STRUCTURE:
  All files: {files_text}

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
        return f"{_WEB_SYSTEM_PROMPT}\n\n{user_prompt}"

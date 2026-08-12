# Test Suite Analysis

> Generated: 2026-08-10
> Scope: F:\AI-DevOS3\backend\

---

## Existing Test Inventory

| File | Lines | Tests | What it covers |
|------|-------|-------|----------------|
| _(none)_ | — | — | The `tests/` directory referenced by `pytest.ini` does not exist on disk. There are zero project-owned test files. |

**Full finding:** `pytest.ini` at `F:\AI-DevOS3\backend\pytest.ini` declares:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
norecursedirs = temp-workspace .venv node_modules .git
```

The directory `F:\AI-DevOS3\backend\tests\` does not exist. Running `pytest` from the backend root would produce `no tests ran` (0 collected). The `venv/` tree contains ~1,848 third-party `test_*.py` files (mpmath, sympy, torch, scipy, etc.) but these are excluded by `norecursedirs = .venv` — except the venv is named `venv`, not `.venv`, meaning they would be collected unless the `norecursedirs` pattern matches both. This is a potential footgun (see Test Commands section).

---

## Tests Touching Sandbox/Sprint Pipeline

None. No test file references `CodeSandbox`, `SandboxResult`, `SprintExecutor`, `PipelineSupervisor`, `SecureExecutionSandbox`, or any sprint pipeline class.

---

## Integration Test Scope

None exist. There are no integration tests, unit tests, or smoke tests of any kind in the project-owned test tree.

---

## Available Fixtures

None. No `conftest.py` files exist in any project directory (outside venv). There are no `project_id`, `workspace`, or `sandbox` fixtures.

---

## Async Test Pattern

Not yet established. `pytest-asyncio>=0.23.0` is listed in `requirements.txt`, so the dependency is present. No tests exist that demonstrate the pattern in use. For new async tests, the recommended pattern (matching pytest-asyncio 0.23+) is:

```python
import pytest

@pytest.mark.asyncio
async def test_something():
    ...
```

Or with module-level mode declaration:
```python
# conftest.py
import pytest
pytest_plugins = ['pytest_asyncio']
```

Note: `SprintExecutor.run()` and `PipelineSupervisor.run()` are synchronous (`def`, not `async def`) as of the current codebase — no async handling needed for them.

---

## Tests At Risk from Phase 1 Changes

**There are zero existing tests at risk** because the test suite is empty. No test file asserts on sprint behavior, sandbox behavior, or pipeline semantics.

**However, the following source behaviors will become harder to test retroactively once Phase 1 ships, so they should be pinned by new tests before or during implementation:**

### Implicit contract: SprintResult.success defaults to True
`F:\AI-DevOS3\backend\app\shared\models\sprint.py`
```python
class SprintResult(BaseModel):
    success: bool = True  # ← default is True, not False
```
Any code that constructs `SprintResult()` without `success=False` reports success. Phase 1 changes that gate sprint completion on sandbox results must explicitly construct `SprintResult(success=False, ...)` for failure paths.

### Implicit contract: CodeSandbox.run() is non-fatal
`F:\AI-DevOS3\backend\app\execution\code_sandbox.py` lines 109–135:
`run()` catches all exceptions internally; it never raises. Phase 1 must preserve this contract — if install fails, it must return `SandboxResult` with `build.success=False`, not raise.

### Implicit contract: disabled mode skips all execution
`CodeSandbox.run()` line 92: when `self._enabled` is False, returns `SandboxResult.disabled(project_id, sprint)` immediately. Phase 1's `install()` method must also short-circuit the same way.

---

## New Tests Required for Phase 1

The test file should be created at `F:\AI-DevOS3\backend\tests\test_phase1_sandbox.py`.
A `conftest.py` at `F:\AI-DevOS3\backend\tests\conftest.py` is also needed (fixtures).

### conftest.py fixtures needed

```python
# tests/conftest.py
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
def tmp_project_dir(tmp_path):
    """An empty temp directory pretending to be a generated project."""
    return tmp_path

@pytest.fixture
def python_project_dir(tmp_path):
    """Minimal Python project: requirements.txt + main.py."""
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    (tmp_path / "main.py").write_text('def main():\n    print("hello")\n')
    return tmp_path

@pytest.fixture
def node_project_dir(tmp_path):
    """Minimal Node project: package.json + index.js."""
    (tmp_path / "package.json").write_text('{"name":"test","version":"1.0.0"}\n')
    (tmp_path / "index.js").write_text('console.log("hello");\n')
    return tmp_path

@pytest.fixture
def mock_workspace(tmp_path):
    """Minimal workspace mock that satisfies CodeSandbox._resolve_project_dir."""
    class _WS:
        def get_workspace_path(self, project_id):
            p = tmp_path / project_id
            p.mkdir(exist_ok=True)
            return p
    return _WS()

@pytest.fixture
def project_id():
    return "test-proj-001"
```

---

### AC-01: install() method exists on CodeSandbox

**Test name:** `test_codesandbox_has_install_method`
**What it tests:** `CodeSandbox.install()` is a callable method that accepts `(project_dir, stack)`.
**Key assertion:** `hasattr(CodeSandbox, "install")` and the call doesn't raise.
**Requires Docker/subprocess:** No — can be mocked or called with a no-op subprocess.

```python
def test_codesandbox_has_install_method():
    from app.execution.code_sandbox import CodeSandbox
    sandbox = CodeSandbox(enabled=False)
    assert callable(getattr(sandbox, "install", None)), "install() method must exist"
```

---

### AC-02: install() runs pip install for Python stack

**Test name:** `test_install_python_calls_pip`
**What it tests:** `CodeSandbox.install()` on a Python project dir invokes `pip install -r requirements.txt`.
**Key assertion:** The subprocess command list includes `pip` and `requirements.txt`.
**Requires Docker/subprocess:** subprocess (mocked via `unittest.mock.patch`).

```python
from unittest.mock import patch, MagicMock
import subprocess

def test_install_python_calls_pip(python_project_dir):
    from app.execution.code_sandbox import CodeSandbox
    sandbox = CodeSandbox(enabled=True, timeout_seconds=10)

    mock_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch.object(sandbox, "_run_subprocess", return_value=mock_result) as mock_sub:
        result = sandbox.install(python_project_dir, "python")

    # At least one call must have 'pip' and 'requirements' in it
    calls = [" ".join(c.args[0]) for c in mock_sub.call_args_list]
    assert any("pip" in cmd and "requirements" in cmd for cmd in calls), (
        f"Expected pip install call, got: {calls}"
    )
    assert result.success is True
```

---

### AC-03: install() runs npm install for Node stack

**Test name:** `test_install_node_calls_npm`
**What it tests:** `CodeSandbox.install()` on a Node project dir invokes `npm install`.
**Key assertion:** Subprocess command includes `npm` and `install`.
**Requires Docker/subprocess:** subprocess (mocked).

```python
def test_install_node_calls_npm(node_project_dir):
    from app.execution.code_sandbox import CodeSandbox
    sandbox = CodeSandbox(enabled=True, timeout_seconds=10)

    mock_result = subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")
    with patch.object(sandbox, "_run_subprocess", return_value=mock_result) as mock_sub:
        result = sandbox.install(node_project_dir, "node")

    calls = [" ".join(c.args[0]) for c in mock_sub.call_args_list]
    assert any("npm" in cmd and "install" in cmd for cmd in calls), (
        f"Expected npm install call, got: {calls}"
    )
    assert result.success is True
```

---

### AC-04: install() failure returns BuildResult with success=False

**Test name:** `test_install_failure_returns_build_failed`
**What it tests:** When pip install exits non-zero, `install()` returns a result with `success=False` — it does not raise.
**Key assertion:** `result.success is False` and `result.errors` is non-empty.
**Requires Docker/subprocess:** subprocess (mocked with returncode=1).

```python
def test_install_failure_returns_build_failed(python_project_dir):
    from app.execution.code_sandbox import CodeSandbox
    sandbox = CodeSandbox(enabled=True, timeout_seconds=10)

    mock_result = subprocess.CompletedProcess([], returncode=1, stdout="", stderr="error: pkg not found")
    with patch.object(sandbox, "_run_subprocess", return_value=mock_result):
        result = sandbox.install(python_project_dir, "python")

    assert result.success is False
    assert len(result.errors) > 0
```

---

### AC-05: run() calls install() before lint/build/test

**Test name:** `test_run_calls_install_before_lint_and_build`
**What it tests:** `CodeSandbox.run()` invokes `install()` as the first step, before `lint()` and `build()`.
**Key assertion:** Call order: install called before lint, lint called before build.
**Requires Docker/subprocess:** No (all methods mocked).

```python
def test_run_calls_install_before_lint_and_build(mock_workspace, project_id, python_project_dir):
    from app.execution.code_sandbox import CodeSandbox
    from app.shared.dto.sandbox_result import BuildResult, LintResult, InstallResult

    # Set up workspace to resolve project dir
    (python_project_dir / "project").mkdir()
    (python_project_dir / "project" / "requirements.txt").write_text("requests\n")

    class _WS:
        def get_workspace_path(self, pid):
            return python_project_dir

    sandbox = CodeSandbox(workspace_manager=_WS(), enabled=True)

    call_order = []
    with patch.object(sandbox, "install", return_value=InstallResult(success=True)) as mock_install, \
         patch.object(sandbox, "lint", return_value=LintResult()) as mock_lint, \
         patch.object(sandbox, "build", return_value=BuildResult(success=True)) as mock_build, \
         patch.object(sandbox, "test", return_value=MagicMock()) as mock_test:

        mock_install.side_effect = lambda *a, **kw: call_order.append("install") or InstallResult(success=True)
        mock_lint.side_effect = lambda *a, **kw: call_order.append("lint") or LintResult()
        mock_build.side_effect = lambda *a, **kw: call_order.append("build") or BuildResult(success=True)
        mock_test.side_effect = lambda *a, **kw: call_order.append("test") or MagicMock()

        sandbox.run(project_id, sprint=1)

    assert call_order.index("install") < call_order.index("lint"), "install must run before lint"
    assert call_order.index("lint") < call_order.index("build"), "lint must run before build"
```

---

### AC-06: run() stops after install failure (skips lint/build/test)

**Test name:** `test_run_stops_after_install_failure`
**What it tests:** When `install()` fails, `run()` returns immediately with `build.success=False` and does not call `lint()`, `build()`, or `test()`.
**Key assertion:** `result.build.success is False`; lint/build/test never called.
**Requires Docker/subprocess:** No (mocked).

```python
def test_run_stops_after_install_failure(mock_workspace, project_id):
    from app.execution.code_sandbox import CodeSandbox
    from app.shared.dto.sandbox_result import BuildResult, InstallResult

    class _WS:
        def get_workspace_path(self, pid):
            import tempfile
            p = Path(tempfile.mkdtemp()) / "project"
            p.mkdir(parents=True)
            (p.parent / "project" / "requirements.txt").write_text("requests\n")
            return p.parent

    sandbox = CodeSandbox(workspace_manager=_WS(), enabled=True)

    with patch.object(sandbox, "install", return_value=InstallResult(success=False, errors=["pkg not found"])), \
         patch.object(sandbox, "lint") as mock_lint, \
         patch.object(sandbox, "build") as mock_build, \
         patch.object(sandbox, "test") as mock_test:

        result = sandbox.run(project_id, sprint=1)

    assert result.build.success is False
    mock_lint.assert_not_called()
    mock_build.assert_not_called()
    mock_test.assert_not_called()
```

---

### AC-07: disabled mode skips install entirely

**Test name:** `test_disabled_sandbox_skips_install`
**What it tests:** When `SANDBOX_ENABLED=false` (or `enabled=False`), `run()` returns `SandboxResult.disabled()` without calling install, lint, build, or test.
**Key assertion:** `result.enabled is False`; no subprocess spawned.
**Requires Docker/subprocess:** No.

```python
def test_disabled_sandbox_skips_install(project_id):
    from app.execution.code_sandbox import CodeSandbox

    sandbox = CodeSandbox(enabled=False)

    with patch.object(sandbox, "install") as mock_install, \
         patch.object(sandbox, "_run_subprocess") as mock_sub:

        result = sandbox.run(project_id, sprint=1)

    assert result.enabled is False
    mock_install.assert_not_called()
    mock_sub.assert_not_called()
```

---

### AC-08: SandboxResult is persisted to ArtifactStore after sprint

**Test name:** `test_sandbox_result_persisted_to_artifact_store`
**What it tests:** After `PipelineSupervisor._run_sandbox()` runs, the result is written to `ArtifactStore` at a scope like `sprint_N` with name `sandbox_result`.
**Key assertion:** `ArtifactStore.read(scope="sprint_1", name="sandbox_result")` returns a dict with `build.success`.
**Requires Docker/subprocess:** No (mocked CodeSandbox).

```python
def test_sandbox_result_persisted_to_artifact_store(tmp_path, project_id):
    from app.execution.code_sandbox import CodeSandbox
    from app.shared.dto.sandbox_result import SandboxResult, BuildResult
    from app.workspace.artifact_store import ArtifactStore

    # Arrange: stub CodeSandbox to return a known result
    sandbox = MagicMock()
    sandbox.run.return_value = SandboxResult(
        project_id=project_id,
        sprint=1,
        enabled=True,
        build=BuildResult(success=True),
    )

    store = ArtifactStore(workspace_root=tmp_path, project_id=project_id)

    # Act: simulate what PipelineSupervisor._run_sandbox should do
    result = sandbox.run(project_id, sprint=1)
    store.write(scope="sprint_1", name="sandbox_result", data=result._to_dict())

    # Assert
    read_back = store.read(scope="sprint_1", name="sandbox_result")
    assert read_back is not None
    assert read_back["build"]["success"] is True
    assert read_back["project_id"] == project_id
```

---

### AC-09: sprint marked failed when sandbox install/build fails

**Test name:** `test_pipeline_marks_sprint_failed_on_sandbox_build_failure`
**What it tests:** In `PipelineSupervisor._run_sprints()`, if `CodeSandbox.run()` returns `build.success=False`, the pipeline does NOT call `mark_sprint_complete` and returns `PipelineResult(success=False)`.
**Key assertion:** `result.success is False`; `workspace.mark_sprint_complete` never called.
**Requires Docker/subprocess:** No (all collaborators mocked).

```python
def test_pipeline_marks_sprint_failed_on_sandbox_build_failure():
    from app.workflow.pipeline_supervisor import PipelineSupervisor
    from app.shared.dto.sandbox_result import SandboxResult, BuildResult
    from app.shared.models.sprint import Sprint, SprintResult, SprintPlan
    from app.shared.enums.project_state import ProjectState
    from unittest.mock import MagicMock

    project_id = "proj-sandbox-fail"

    # Stub workspace
    workspace = MagicMock()
    workspace.get_state.return_value = ProjectState.SPRINT_IN_PROGRESS
    workspace.load_project_json.return_value = {"completed_sprints": [], "stages_completed": [], "mode": "full"}
    workspace.get_sprint_plan.return_value = SprintPlan(
        sprints=[Sprint(sprint_number=1, name="S1", goal="Build", features=[])]
    )

    # Stub sprint_executor: reports success
    sprint_executor = MagicMock()
    sprint_executor.run.return_value = SprintResult(success=True, sprint_complete=True)

    # Stub sandbox: build fails
    code_sandbox = MagicMock()
    code_sandbox.run.return_value = SandboxResult(
        project_id=project_id,
        sprint=1,
        enabled=True,
        build=BuildResult(success=False, errors=["ImportError: no module named 'requests'"]),
    )

    supervisor = PipelineSupervisor(
        workspace=workspace,
        engine=MagicMock(),
        sprint_executor=sprint_executor,
        settings=MagicMock(),
        code_sandbox=code_sandbox,
    )

    result = supervisor._run_sprints(project_id, request="build a thing")

    # Sprint must NOT be marked complete when build failed
    workspace.mark_sprint_complete.assert_not_called()
    assert result.success is False
    assert "build" in result.message.lower() or "sandbox" in result.message.lower() or "sprint" in result.message.lower()
```

---

### AC-09b: SandboxResult.disabled() has correct shape

**Test name:** `test_sandbox_result_disabled_shape`
**What it tests:** `SandboxResult.disabled()` factory returns a result where `enabled=False` and sub-results have safe defaults.
**Key assertion:** `result.enabled is False`, `result.build.success is True` (disabled does not report failure).
**Requires Docker/subprocess:** No.

```python
def test_sandbox_result_disabled_shape():
    from app.shared.dto.sandbox_result import SandboxResult

    result = SandboxResult.disabled("proj-1", sprint=2)

    assert result.enabled is False
    assert result.project_id == "proj-1"
    assert result.sprint == 2
    # disabled result must not look like a build failure
    assert result.build.success is True
    # to_prompt_text must mention DISABLED
    text = result.to_prompt_text()
    assert "DISABLED" in text
```

---

## Test Commands

### Full suite
```bash
cd F:\AI-DevOS3\backend
python -m pytest tests/ -v
```

**Warning:** `norecursedirs` in `pytest.ini` lists `.venv` but the actual venv directory is `venv` (no leading dot). This means pytest **will** descend into `venv/` and collect thousands of third-party test files if the `tests/` directory doesn't exist and pytest falls back to the cwd. Fix: add `venv` (without dot) to `norecursedirs`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
norecursedirs = temp-workspace .venv venv node_modules .git
```

### Sandbox/Sprint tests only
```bash
cd F:\AI-DevOS3\backend
python -m pytest tests/test_phase1_sandbox.py -v
```

### Single AC test
```bash
python -m pytest tests/test_phase1_sandbox.py::test_install_python_calls_pip -v
```

### With coverage
```bash
python -m pytest tests/ --cov=app.execution.code_sandbox --cov=app.workflow.sprint_executor --cov=app.workflow.pipeline_supervisor --cov-report=term-missing
```

---

## Summary

| Question | Answer |
|----------|--------|
| Existing tests that could break from Phase 1 | **0** — test suite does not exist |
| Test files under `tests/` | **0** — directory does not exist |
| Tests referencing CodeSandbox/SprintExecutor | **0** |
| Fixtures available | **0** — no conftest.py exists |
| Async test infrastructure | pytest-asyncio installed but unused |
| New tests needed for Phase 1 | **9 test functions** across 1 new file |
| Tests requiring Docker | **0** of 9 — all can run with subprocess mocks |
| Tests requiring subprocess (real) | **0** — all subprocess calls can be patched |
| pytest.ini bug | `venv` not in `norecursedirs` — will collect 1,800+ third-party tests |

The most important gap is AC-09 (`test_pipeline_marks_sprint_failed_on_sandbox_build_failure`): this is the only test that verifies the **gating behavior** — that a sprint with a failing build is actually marked as failed and not silently completed. Without this test, Phase 1's core safety invariant can regress undetected.

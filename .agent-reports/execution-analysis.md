# Execution Architecture Analysis

---

## SANDBOX_ENABLED Behavior

**Finding:** `SANDBOX_ENABLED` gates ALL execution — not just Docker vs subprocess. When the flag is `false` (the default), `run()` returns immediately with a disabled marker; no subprocess is ever spawned. When `true`, Docker is attempted first via `SecureExecutionSandbox`; if Docker is unavailable, the same `_run_subprocess()` helper is used directly (subprocess fallback). The flag controls whether any verification happens at all, not just which backend executes it.

**Evidence:**
```python
# code_sandbox.py line 35
_SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false").lower() in ("true", "1", "yes")

# code_sandbox.py lines 91-92 — inside run()
if not self._enabled:
    return SandboxResult.disabled(project_id, sprint)

# code_sandbox.py lines 69-78 — Docker is tried only when enabled=True
if self._enabled:
    try:
        from .sandbox import SecureExecutionSandbox
        self._docker_sandbox = SecureExecutionSandbox(default_image=_DOCKER_PYTHON)
        if not self._docker_sandbox.is_available():
            logger.info("[CodeSandbox] Docker not available — subprocess fallback only")
            self._docker_sandbox = None
    except Exception as exc:
        ...
        self._docker_sandbox = None
```

Note: `_docker_sandbox` is set but never actually used in `lint()`, `build()`, or `test()` — all three methods call `_run_subprocess()` directly. The Docker object is only used indirectly in `verify_dockerfile()`. So the subprocess fallback is the only path currently active even when `SANDBOX_ENABLED=true` and Docker is present.

**File:** `F:\AI-DevOS3\backend\app\execution\code_sandbox.py`
**Function:** `CodeSandbox.__init__()`, `CodeSandbox.run()`
**Impact:** The default `SANDBOX_ENABLED=false` means every sprint runs zero verification. Lint, build, and test are structurally complete but never invoked in production.
**Recommendation:** Set `SANDBOX_ENABLED=true` in `.env`. No code change required to activate subprocess execution; it is the live path already.
**Confidence:** High

---

## install() Method Status

**Finding:** There is NO `install()` method on `CodeSandbox`. The class exposes `run()`, `syntax_check()`, `lint()`, `build()`, `test()`, and `verify_dockerfile()`. There is no step that runs `pip install -r requirements.txt` or `npm install` before `build()` or `test()` execute. As a result, `_test_python()` will call `pytest` against a directory whose dependencies have never been installed, producing `ModuleNotFoundError` failures that are indistinguishable from real test failures.

**Evidence:**
```python
# code_sandbox.py lines 283-292 — _test_python() runs pytest with no prior install step
def _test_python(self, project_dir: Path, started: float) -> TestResult:
    """Run pytest with JSON output."""
    tests_dir = project_dir / "tests"
    if not tests_dir.exists():
        return TestResult(total=0)
    cmd = ["pytest", str(tests_dir), "--tb=short", "-q", "--no-header"]
    proc = self._run_subprocess(cmd, cwd=project_dir)
    ...

# code_sandbox.py lines 266-281 — _build_python() calls py_compile, not pip
def _build_python(self, project_dir: Path, started: float) -> BuildResult:
    """Try to import the generated app entry point as a syntax check."""
    entry = self._find_python_entry(project_dir)
    cmd = ["python", "-m", "py_compile", str(entry)]
    proc = self._run_subprocess(cmd, cwd=project_dir)
```

The pattern `build()` and `test()` use is: a public method dispatches to a private `_<check>_<stack>()` helper, which builds a `cmd` list and calls `self._run_subprocess(cmd, cwd=project_dir)`, then parses stdout/stderr into a typed result object.

**File:** `F:\AI-DevOS3\backend\app\execution\code_sandbox.py`
**Function:** `CodeSandbox._test_python()`, `CodeSandbox._build_python()`
**Impact:** Without an install step, `pytest` and `npm test` will fail with import/module-not-found errors for any project that has third-party dependencies (i.e., all real projects). The `BuildResult` and `TestResult` will show failures that are infrastructure failures, not code failures, misleading BugAnalyst.
**Recommendation:** Add `install()` as a public method and call it in `run()` immediately after `detect_stack()`, before `lint()`. Minimal implementation:
```python
def install(self, project_dir: Path, stack: str) -> bool:
    """Install project dependencies. Returns True on success."""
    if stack == "python":
        req = project_dir / "requirements.txt"
        if req.exists():
            proc = self._run_subprocess(
                ["pip", "install", "-r", str(req), "--quiet"], cwd=project_dir
            )
            return proc.returncode == 0
    elif stack == "node":
        proc = self._run_subprocess(["npm", "install", "--prefer-offline"], cwd=project_dir)
        return proc.returncode == 0
    return True  # unknown stack — nothing to install
```
Then in `run()` after `detect_stack()`: `self.install(project_dir, stack)`.
**Confidence:** High

---

## CodeSandbox.run() Signature and Return

**Finding:** `run()` takes `project_id: str` and `sprint: int = 0` and always returns a `SandboxResult`. It never raises. There are four distinct return paths:

1. **Disabled** (`_enabled=False`): returns `SandboxResult.disabled(project_id, sprint)` — `enabled=False`, lint/test/build are default-empty.
2. **Unresolvable workspace**: returns `SandboxResult(enabled=True, build=BuildResult(success=False, errors=["Could not resolve project workspace directory"]))`.
3. **Build failure**: returns a partial result — `lint` is populated, `build.success=False`, `test` is the default empty `TestResult` (tests are skipped).
4. **Full run**: returns `SandboxResult` with all three sub-results populated.

**Evidence:**
```python
# code_sandbox.py line 84
def run(self, project_id: str, sprint: int = 0) -> SandboxResult:

# Return on disabled (line 92):
return SandboxResult.disabled(project_id, sprint)

# Return on unresolvable dir (lines 97-102):
return SandboxResult(
    project_id=project_id, sprint=sprint, enabled=True,
    build=BuildResult(success=False, errors=["Could not resolve project workspace directory"]),
)

# Stop after build failure (lines 121-123):
if not result.build.success:
    logger.info("[CodeSandbox] stopping after build failure, skipping tests")
    return result
```

**File:** `F:\AI-DevOS3\backend\app\execution\code_sandbox.py`
**Function:** `CodeSandbox.run()`
**Impact:** The non-raising contract is correct. However, the early return on build failure means that a dependency install failure (currently not implemented) would be silently absorbed as a build failure, and tests would never run.
**Confidence:** High

---

## SandboxResult Fields

**Finding:** `SandboxResult` is a dataclass in `shared/dto/sandbox_result.py` with the following fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `project_id` | `str` | (required) | |
| `sprint` | `int` | (required) | |
| `ran_at` | `str` | UTC ISO timestamp | auto-generated |
| `stack` | `str` | `"unknown"` | `"python"` \| `"node"` \| `"unknown"` |
| `enabled` | `bool` | `True` | `False` when sandbox disabled |
| `lint` | `LintResult` | empty `LintResult` | |
| `test` | `TestResult` | empty `TestResult` | |
| `build` | `BuildResult` | empty `BuildResult` | |

**LintResult fields:** `errors: list[dict]` (each: `{file, line, message}`), `error_count: int`, `duration_ms: int`, `stdout: str`, `stderr: str`

**TestResult fields:** `passed: int`, `failed: int`, `total: int`, `failures: list[dict]` (each: `{test_name, error}`), `duration_ms: int`, `stdout: str`, `stderr: str`

**BuildResult fields:** `success: bool` (default `True`), `errors: list[str]`, `duration_ms: int`, `stdout: str`, `stderr: str`

**Evidence:**
```python
# shared/dto/sandbox_result.py lines 82-96
@dataclass
class SandboxResult:
    project_id: str
    sprint: int
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stack: str = "unknown"
    enabled: bool = True
    lint: LintResult = field(default_factory=LintResult)
    test: TestResult = field(default_factory=TestResult)
    build: BuildResult = field(default_factory=BuildResult)
```

**File:** `F:\AI-DevOS3\backend\app\shared\dto\sandbox_result.py`
**Function:** `SandboxResult`, `LintResult`, `TestResult`, `BuildResult`
**Impact:** The DTO is complete and has `to_json()` and `to_prompt_text()` methods ready for persistence and LLM injection. No changes needed to the data model.
**Confidence:** High

---

## Existing Sprint Pipeline → CodeSandbox Coupling

**Finding:** `PipelineSupervisor` has a `self._code_sandbox` slot that accepts a `CodeSandbox` instance at construction time via `code_sandbox=None`. If `None` (likely the default in the DI container), `_run_sandbox()` returns immediately without calling `CodeSandbox.run()`. The sandbox IS wired into the pipeline at the right point (after each sprint, before the release phase), but only if a non-None instance is passed in. `SprintExecutor` has zero references to `CodeSandbox` — it is entirely outside the sprint phase.

**Evidence:**
```python
# pipeline_supervisor.py line 153 — constructor parameter
code_sandbox=None,

# pipeline_supervisor.py line 164
self._code_sandbox = code_sandbox

# pipeline_supervisor.py lines 455-456 — syntax check in sprint phase
if sprint_result.success and self._code_sandbox is not None:
    syntax_errors = self._code_sandbox.syntax_check(project_id, sprint=n)

# pipeline_supervisor.py line 500 — full sandbox in sprint phase
self._run_sandbox(project_id, sprint_number=n)

# pipeline_supervisor.py lines 844-846 — _run_sandbox guard
if self._code_sandbox is None:
    return
```

`SprintExecutor` grep result: zero matches for `sandbox`, `CodeSandbox`, or `code_sandbox`.

**File:** `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`, `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`
**Function:** `PipelineSupervisor.__init__()`, `PipelineSupervisor._run_sandbox()`
**Impact:** Even with `SANDBOX_ENABLED=true`, if the DI container constructs `PipelineSupervisor` without a `CodeSandbox` instance, no sandbox execution occurs. The wiring point exists and is correct; the instance just needs to be injected.
**Recommendation:** Check the DI container / factory that constructs `PipelineSupervisor` and ensure it passes `code_sandbox=CodeSandbox(workspace_manager=...)`.
**Confidence:** High

---

## Bug-Fix Loop — Failure Input Format

**Finding:** BugAnalyst receives sandbox results as a **pre-formatted plain string**, not a typed `SandboxResult`. There are two injection paths:

1. **Direct call** (`bug_analyst.analyse(sandbox_results=...)`): expects a `str` produced by `SandboxResult.to_prompt_text()`.
2. **Context assembler** (`_inject_sandbox_results()` in `context_assembler.py`): reads raw JSON from `memory_manager.load(project_id, "sandbox:latest")`, manually formats it into a `## AUTOMATED VERIFICATION RESULTS` markdown block, and prepends it to the prompt content.

The bug-fix loop in `PipelineSupervisor` reads BugAnalyst's `result.artifact.structured_content` and extracts `type`, `affected_agent`, and `targeted_fix_instruction` — it does NOT re-read `SandboxResult` during the fix iteration. The fix instruction is passed as a plain string to the downstream stage (`engine.run(project_id, _resolve(target_stage), fix_content)`).

**Evidence:**
```python
# bug_analyst.py lines 182, 186-198
def analyse(self, ..., sandbox_results: str = "") -> dict:
    """...accepts sandbox_results (pre-formatted text from SandboxResult.to_prompt_text())"""
    if sandbox_results:
        parts.append(f"REAL EXECUTION RESULTS (sandbox lint/test/build):\n{sandbox_results}")

# context_assembler.py lines 343-376 — second injection path
def _inject_sandbox_results(self, project_id, stage_name, content):
    if stage_name != Stage.BugAnalyst.value or self._memory_manager is None:
        return content
    sandbox_json = self._memory_manager.load(project_id, "sandbox:latest")
    data = json.loads(sandbox_json) if isinstance(sandbox_json, str) else sandbox_json
    # ... manually builds markdown text from dict fields

# pipeline_supervisor.py lines 648-668 — bug-fix loop reads structured artifact, not SandboxResult
elif bug_type == "code_bug":
    bug_fix_iterations += 1
    affected = structured.get("affected_agent", "Backend")
    fix = structured.get("targeted_fix_instruction", "")
    fix_content = f"A bug was found. Your task is to apply the following fix: {fix}"
    self.engine.run(project_id, _resolve(target_stage), fix_content)
```

**File:** `F:\AI-DevOS3\backend\app\agents\bug_analyst.py`, `F:\AI-DevOS3\backend\app\workflow\context_assembler.py`, `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`
**Function:** `BugAnalystAgent.analyse()`, `ContextAssembler._inject_sandbox_results()`, `PipelineSupervisor._run_release_pipeline()`
**Impact:** The fix loop currently passes only a text instruction string to the stage agent. It does not re-run the sandbox after applying a fix to confirm the fix worked, nor does it pass structured failure data. This means the loop is LLM-opinion-driven, not verification-driven: it will cycle up to `_MAX_BUG_FIX_ITERATIONS` times without confirming whether fixes actually resolved test failures.
**Confidence:** High

---

## detect_stack() Supported Stacks

**Finding:** `detect_stack()` returns exactly one of three string literals: `"python"`, `"node"`, or `"unknown"`. It inspects the top two directory levels (project root + immediate subdirectories) for known marker files.

| Return value | Trigger files |
|---|---|
| `"python"` | `requirements.txt` OR `setup.py` OR `pyproject.toml` |
| `"node"` | `package.json` |
| `"unknown"` | none of the above found |

When stack is `"unknown"`: `lint()` returns an empty `LintResult`, `build()` returns `BuildResult(success=True)`, `test()` returns an empty `TestResult`. Verification is silently skipped.

**Evidence:**
```python
# code_sandbox.py lines 195-206
def detect_stack(self, project_dir: Path) -> str:
    """Return "python", "node", or "unknown" by inspecting generated files."""
    subdirs = list(project_dir.iterdir()) if project_dir.is_dir() else []
    for candidate in [project_dir, *subdirs]:
        if not isinstance(candidate, Path):
            continue
        if (candidate / "requirements.txt").exists() or (candidate / "setup.py").exists() or (candidate / "pyproject.toml").exists():
            return "python"
        if (candidate / "package.json").exists():
            return "node"
    return "unknown"
```

**File:** `F:\AI-DevOS3\backend\app\execution\code_sandbox.py`
**Function:** `CodeSandbox.detect_stack()`
**Impact:** Projects without a `requirements.txt`, `setup.py`, `pyproject.toml`, or `package.json` at root or first-level subdirectory will silently get `"unknown"` and skip all verification. This is a silent skip, not a reported failure.
**Confidence:** High

---

## Summary: What Blocks Automatic Verification

- **`SANDBOX_ENABLED` defaults to `false`** — the primary gate. `run()` returns a disabled marker immediately without spawning a single process. Every sprint completes with zero real verification. Evidence: `code_sandbox.py` line 35 (`"false"` default) and line 92 (early return).

- **No `install()` step** — even when the sandbox is enabled, `_test_python()` invokes `pytest` and `_test_node()` invokes `npx jest` against directories whose third-party dependencies have never been installed. Any project with a `requirements.txt` will produce `ModuleNotFoundError` failures on every test run, making sandbox output useless noise. Evidence: `code_sandbox.py` lines 283-293 (`_test_python` has no `pip install` step).

- **`CodeSandbox` instance not injected into `PipelineSupervisor`** — if the DI container constructs `PipelineSupervisor(code_sandbox=None)` (the default), `_run_sandbox()` exits immediately at line 845 even when `SANDBOX_ENABLED=true`. The wiring point exists; the instance is absent.

- **Bug-fix loop is not verification-gated** — after applying a `code_bug` fix, the pipeline does not re-run the sandbox to confirm the fix resolved the actual failure. The loop iterates based on BugAnalyst's LLM opinion, not on `SandboxResult.test.failed == 0`. Evidence: `pipeline_supervisor.py` lines 658-668 (fix applied, no re-sandbox call).

- **Silent skip for unknown stacks** — projects that do not land `requirements.txt`, `setup.py`, `pyproject.toml`, or `package.json` at root or one level deep get `stack="unknown"` and all three checks (`lint`, `build`, `test`) return empty/success results. No error is reported. Evidence: `code_sandbox.py` lines 215, 223-224, 233.

---

## Minimal Changes Required

1. **Set `SANDBOX_ENABLED=true` in `.env`** — no code change. This is the single-line flip that activates the subprocess path. All the subprocess logic for lint, build, and test already exists and is correct.

2. **Wire `CodeSandbox` into `PipelineSupervisor`** — in the DI container or factory that constructs `PipelineSupervisor`, pass `code_sandbox=CodeSandbox(workspace_manager=workspace_manager)`. No changes to `PipelineSupervisor` itself; only the construction call site.

3. **Add `install()` method to `CodeSandbox` and call it in `run()`** — insert between `detect_stack()` and the `lint()` call. The method should run `pip install -r requirements.txt --quiet` (Python) or `npm install --prefer-offline` (Node) via the existing `_run_subprocess()` helper. A failed install should be recorded in `SandboxResult` (suggest adding an `install: InstallResult` field) but should not abort the run — lint and build (py_compile) can still run without deps, only pytest needs them.

4. **Re-run sandbox after each bug-fix iteration** — in `PipelineSupervisor._run_release_pipeline()`, after `self.engine.run(project_id, _resolve(target_stage), fix_content)` applies a code_bug fix, call `self._run_sandbox(project_id, sprint_number=sprint_number)` so the next BugAnalyst pass reads updated execution results rather than stale pre-fix results.

5. **Log a warning (not silent skip) when stack is `"unknown"`** — replace the silent empty returns in `lint()`, `build()`, and `test()` for the unknown-stack case with a `logger.warning()` so operators know detection failed. No change to return values needed.

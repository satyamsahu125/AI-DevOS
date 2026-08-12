# Audit 1: Phase 1 Execution Verification

**Auditor**: Principal Technical Auditor (read-only, no prior reports trusted)
**Date**: 2026-08-10
**Files read**: code_sandbox.py, sandbox_result.py, sprint_executor.py, pipeline_supervisor.py, manager.py, test_phase1_sandbox.py

---

## AC-01: Dependency Installation

**Verdict: PASS**

`CodeSandbox.install()` exists at `code_sandbox.py:270–287`. It dispatches to `_install_python()` (pip) or `_install_node()` (npm), and returns `BuildResult(success=True)` for unknown stacks (no-op).

`run()` calls `install()` at line 131 — before lint, build, or test. Install failure causes immediate return with build marked failed and lint/build/test skipped (`code_sandbox.py:136–147`).

No requirements.txt: `_install_python()` calls `_find_requirements_file()` which searches root and one level deep. If nothing found, returns `BuildResult(success=True, duration_ms=0)` without calling pip (`code_sandbox.py:309–313`). Pipeline continues.

**Evidence (install call order)**:
```python
# code_sandbox.py:130–147
result.install = self.install(project_dir, stack)
...
if not result.install.success:
    result.build = BuildResult(
        success=False,
        errors=result.install.errors,
        ...
    )
    return result
```

---

## AC-02: Build Capture

**Verdict: PASS**

`build()` is called at `code_sandbox.py:158` — after lint, before test. Order is install → lint → build → test.

Build failure propagates correctly: `_build_python()` returns `BuildResult(success=False, errors=errors, ...)` at line 428. `run()` checks `result.build.success` at line 163 and returns early if False, skipping tests. The returned `SandboxResult.build.success` is `False`.

**Evidence**:
```python
# code_sandbox.py:156–165
result.build = self.build(project_dir, stack)
...
if not result.build.success:
    logger.info("[CodeSandbox] stopping after build failure, skipping tests: ...")
    return result
```

---

## AC-03: Test Execution and Structured Results

**Verdict: PASS (with documented skip condition)**

`test()` is called at `code_sandbox.py:169` — only after build succeeds. `TestResult` is populated with `passed`, `failed`, `total`, `failures`, `duration_ms`, `stdout`, `stderr` fields (`sandbox_result.py:43–48`).

Tests are skipped when `tests/` directory does not exist: `_test_python()` returns `TestResult(total=0)` if `tests_dir` is absent (`code_sandbox.py:432–434`). This is documented behavior and returns a result indicating no tests were found rather than a passing result.

**Evidence**:
```python
# code_sandbox.py:430–434
def _test_python(self, project_dir: Path, started: float) -> TestResult:
    tests_dir = project_dir / "tests"
    if not tests_dir.exists():
        return TestResult(total=0)
```

---

## AC-04: Result Persistence

**Verdict: PASS**

`_persist_sandbox_result()` exists in `SprintExecutor` at `sprint_executor.py:330–359`. It is called at line 292 inside `_run_sandbox_verification()`, immediately after `code_sandbox.run()` returns. ArtifactStore scope is `f"sprint_{sprint_number}"`, name is `"sandbox_result"`.

`SandboxResult.from_dict()` exists at `sandbox_result.py:156–195`. It is tolerant of missing fields (e.g. old persisted results without the `install` field). `_run_sandbox()` in `pipeline_supervisor.py` loads from ArtifactStore at lines 901–914 using `SandboxResult.from_dict(data)` and skips re-running if found.

A restarted process will reconstruct the result correctly as long as ArtifactStore is file-backed (not verified here — depends on ArtifactStore implementation).

**Evidence**:
```python
# sprint_executor.py:344–349
store.write(
    scope=f"sprint_{sprint_number}",
    name="sandbox_result",
    data=sandbox_result._to_dict(),
)
```

---

## AC-05: Build Failure → Sprint Failure

**Verdict: PASS**

Code path is clean and unambiguous:

1. `_run_sandbox_verification()` checks `sandbox_result.build.success` at `sprint_executor.py:297`.
2. If False → returns `(False, "Build failed: ...")`.
3. `run()` receives `sandbox_success = False` at line 131.
4. At lines 134–144: returns `SprintResult(sprint_complete=False, success=False, ...)` immediately.
5. `mark_sprint_complete()` at line 147 is inside the `if all_success:` block and is **never reached**.

**Evidence**:
```python
# sprint_executor.py:127–144
if all_success:
    sandbox_success, sandbox_message = self._run_sandbox_verification(project_id, sprint)
    if not sandbox_success:
        return SprintResult(
            sprint_complete=False,
            all_sprints_complete=False,
            success=False,
            message=f"Sprint {sprint.sprint_number} build/test failed: {sandbox_message}",
        )
    self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
    self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
```

Test confirms: `test_build_failure_causes_sprint_failure` asserts `result.success is False` and `mark_sprint_complete.assert_not_called()` (`test_phase1_sandbox.py:378–403`).

---

## AC-06: Test Failure → Sprint Failure

**Verdict: FAIL**

`_run_sandbox_verification()` checks **only** `sandbox_result.build.success` (`sprint_executor.py:297`). There is no check for `sandbox_result.test.failed > 0` anywhere in this method or in `run()`.

A sprint with 10 failing tests and a passing build will be marked complete. Test results are captured in `SandboxResult.test` and persisted, but they do not gate sprint completion.

**Gap**: `sprint_executor.py:_run_sandbox_verification()` must add:
```python
if sandbox_result.test.failed > 0:
    return False, f"Tests failed: {sandbox_result.test.failed}/{sandbox_result.test.total}"
```

The test suite (`test_phase1_sandbox.py`) also does not have a test for this case — `test_build_success_marks_sprint_complete` passes `TestResult(passed=3, total=3)` but never tests the `failed > 0` branch.

---

## AC-07: Bug-Fix Loop Consumes SandboxResult

**Verdict: PARTIAL**

**What works**: After each sprint, `_run_sandbox()` stores `SandboxResult.to_json()` in `memory_manager` at key `"sandbox:latest"` (`pipeline_supervisor.py:928`). This is available before the Release phase begins.

**Gap**: In `_run_release()`, BugAnalyst is invoked via `self.engine.run(project_id, resolved_stage, request)` at line 579. There is **no explicit injection** of sandbox result data into BugAnalyst's context string — the `request` passed is the original project request, not sandbox output. Whether BugAnalyst reads `"sandbox:latest"` from memory_manager depends entirely on BugAnalyst's agent implementation (not in scope here). The pipeline correctly stores the data, but the wiring from storage to BugAnalyst prompt context is not verified in these files.

**Evidence**:
```python
# pipeline_supervisor.py:579
result = self._run_stage_safe(project_id, stage_key, request)
# 'request' = original project description, NOT sandbox data
```

---

## AC-08: Post-Fix Rebuild/Retest

**Verdict: PASS**

After a `code_bug` fix is applied in `_run_release()`, the code explicitly calls `self._code_sandbox.run(project_id, sprint=current_sprint, require_execution=True)` at `pipeline_supervisor.py:683–688`. This is a fresh execution, not cached.

The fresh result is stored in both memory (`"sandbox:latest"`) and ArtifactStore under `f"sandbox_result_fix_{bug_fix_iterations}"` at lines 688–698.

**Evidence**:
```python
# pipeline_supervisor.py:683–698
fresh_result = self._code_sandbox.run(
    project_id,
    sprint=current_sprint,
    require_execution=True,
)
if self._memory_manager is not None:
    self._memory_manager.store(project_id, "sandbox:latest", fresh_result.to_json())
store.write(
    scope=f"sprint_{current_sprint}",
    name=f"sandbox_result_fix_{bug_fix_iterations}",
    data=fresh_result._to_dict(),
)
```

**Condition**: This only runs when `self._code_sandbox is not None and current_sprint > 0` (line 676). If `current_sprint` is 0 (project.json missing `current_sprint_number`), the re-run is skipped silently.

---

## AC-09: Process Restart Survivability

**Verdict: PARTIAL**

**Persisted (survives restart)**:
- ArtifactStore at `sprint_N/sandbox_result` (written by `SprintExecutor._persist_sandbox_result()`). Loaded by `PipelineSupervisor._run_sandbox()` via `store.read()` + `SandboxResult.from_dict()`.
- ArtifactStore at `sprint_N/sandbox_result_fix_K` (written after each bug-fix iteration).

**Transient (lost on restart)**:
- `memory_manager.store(project_id, "sandbox:latest", ...)` — depends on MemoryManager implementation. If in-memory only, `"sandbox:latest"` is lost. The pipeline does re-load from ArtifactStore in `_run_sandbox()` and re-populates memory, so this is recoverable for the sandbox check. However, if a restart occurs mid-release-phase after sandbox was loaded to memory but before BugAnalyst runs, BugAnalyst may read stale/absent data.

**Evidence**: `_run_sandbox()` has explicit ArtifactStore load-before-run logic at `pipeline_supervisor.py:900–915`, confirming restart-safe behavior for the sandbox result itself.

---

## SANDBOX_ENABLED vs require_execution

**Verdict: Correctly implemented, with a nuance**

`_SANDBOX_ENABLED` is read at module load time (`code_sandbox.py:35`). `CodeSandbox.__init__` uses it to control Docker availability only (`code_sandbox.py:65–78`).

In `run()` at `code_sandbox.py:111`:
```python
if not self._enabled and not require_execution:
    return SandboxResult.disabled(project_id, sprint)
```

`SprintExecutor._run_sandbox_verification()` hardcodes `require_execution=True` at `sprint_executor.py:287`. This means:
- `SANDBOX_ENABLED=false` → Docker not initialized, subprocess fallback only, but execution **always runs** when called from SprintExecutor.
- `SANDBOX_ENABLED=true` → Docker attempted; falls back to subprocess if unavailable.
- `require_execution=False` (default, PipelineSupervisor fallback) + `SANDBOX_ENABLED=false` → returns disabled result (no execution).

**Conclusion**: `SANDBOX_ENABLED` no longer prevents execution when called from SprintExecutor (due to `require_execution=True`). It only controls isolation level (Docker vs subprocess). This matches the documented intent in the docstring.

---

## Double Execution Check

**Verdict: No double execution (correct)**

`PipelineSupervisor._run_sandbox()` (`pipeline_supervisor.py:878–947`) checks ArtifactStore **before** running:

```python
# pipeline_supervisor.py:900–919
if store.exists(f"sprint_{sprint_number}", "sandbox_result"):
    data = store.read(f"sprint_{sprint_number}", "sandbox_result")
    if data:
        sandbox_result = SandboxResult.from_dict(data)
        logger.info("... no re-run ...")
# Fall back only if not already persisted:
if sandbox_result is None:
    sandbox_result = self._code_sandbox.run(project_id, sprint=sprint_number)
```

Since `SprintExecutor._run_sandbox_verification()` persists to ArtifactStore at `sprint_N/sandbox_result` before returning, `_run_sandbox()` will always find it and skip re-execution. Double execution is prevented.

---

## Wiring Check (manager.py → SprintExecutor)

**Verdict: Correctly wired**

In `manager.py:131–142`:
```python
sprint_exec = SprintExecutor(
    engine=self.engine,
    agent_factory=_af,
    workspace_manager=self.workspace_manager,
    artifact_manager=self.artifact_manager,
    sprint_monitor=sprint_monitor,
    broadcaster=self.broadcaster,
    project_writer=getattr(self.engine, "project_writer", None),
    # Phase 1: wire sandbox so SprintExecutor gates sprint success on
    # install → build → test before marking the sprint complete.
    code_sandbox=code_sandbox,
)
```

`code_sandbox` is the same object passed to `WorkflowManager.__init__()`. If the caller passes `code_sandbox=None` (or omits it), `SprintExecutor._code_sandbox` will be `None`, which triggers the backward-compat path at `sprint_executor.py:269–274`: returns `(True, "")` — no execution gate, sprint always passes.

---

## Critical Gaps Found (ordered by severity)

### 1. CRITICAL — AC-06: Test failures do not block sprint completion
**File**: `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`, `_run_sandbox_verification()`, line 297
**Detail**: Only `build.success` is checked. `test.failed > 0` is never evaluated. A sprint with all tests failing will be marked complete as long as the build passes. The Phase 1 claim "install → build → test → accept/reject" is incomplete: the reject path for test failures is missing.
**Fix**: Add after build check — if `sandbox_result.test.failed > 0`, return `(False, f"Tests failed: {sandbox_result.test.failed}/{sandbox_result.test.total}")`.

### 2. HIGH — AC-07: BugAnalyst sandbox data injection is not verified in these files
**File**: `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`, `_run_release()`, line 579
**Detail**: Sandbox result is stored in memory_manager but the context string passed to BugAnalyst's engine run is the original project request, not the sandbox output. Whether BugAnalyst reads memory is opaque to this audit. If BugAnalyst does not read `"sandbox:latest"`, it is operating blind.

### 3. MEDIUM — AC-08: Post-fix sandbox skipped silently when current_sprint = 0
**File**: `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`, line 676
**Detail**: `current_sprint = int(data_for_sprint.get("current_sprint_number", 0))`. If `current_sprint_number` is not written to project.json, the post-fix sandbox re-run is skipped with no error. The fix applies but BugAnalyst's next pass reads stale data.

### 4. MEDIUM — AC-09: MemoryManager transience unknown
**Detail**: `"sandbox:latest"` is stored in `memory_manager` which may be in-memory only. On restart during Release phase, BugAnalyst could read absent data. The ArtifactStore path is durable but `_run_sandbox()` is only called once (during Sprint phase), not at Release phase entry.

### 5. LOW — AC-06 test gap in test suite
**File**: `F:\AI-DevOS3\backend\tests\test_phase1_sandbox.py`
**Detail**: No test covers the case where `build.success=True` but `test.failed > 0`. The test suite would pass even if test-failure-blocking were added, because no regression test protects it.

---

## Overall Phase 1 Verdict

**PARTIAL**

**What is correctly implemented**:
- CodeSandbox.install() exists and is called before lint/build/test (AC-01 ✓)
- Build results are captured and propagated correctly (AC-02 ✓)
- Test execution runs and produces structured TestResult (AC-03 ✓)
- Results are persisted to ArtifactStore with from_dict() round-trip (AC-04 ✓)
- Build failure correctly prevents sprint completion and mark_sprint_complete (AC-05 ✓)
- Post-fix sandbox re-run is implemented and fresh (AC-08 ✓)
- Double execution is prevented by ArtifactStore check-before-run (Double Execution ✓)
- code_sandbox is correctly wired through manager.py → SprintExecutor (Wiring ✓)
- require_execution=True correctly bypasses SANDBOX_ENABLED=false for isolation-only control (SANDBOX_ENABLED ✓)

**What is missing or broken**:
- Test failures (test.failed > 0) do NOT block sprint completion — the "test → reject" half of the AC is not implemented (AC-06 FAIL)
- BugAnalyst's consumption of SandboxResult data cannot be confirmed from these files alone (AC-07 PARTIAL)
- Post-fix rebuild is silently skipped when current_sprint_number absent from project.json (AC-08 edge case)

The core claim — "install → build → accept/reject sprint" — is verified. The extended claim "install → build → **test** → accept/reject sprint" is not, because test failures are captured but not enforced as a sprint gate.

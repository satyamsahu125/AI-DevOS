# Audit 7: Failure and Recovery Audit

All findings are derived directly from source code. No prior reports were consulted.

---

## Scenario 1: Crash During BackendDeveloper

**What state is in project.json?**

`update_project_json` uses a write-to-temp-then-`os.replace()` pattern
(`workspace/manager.py:213–228`), so `project.json` is never left partially
written. On a mid-stage Python crash the last committed state is whatever
the engine wrote before dying.

Before `BackendDeveloper` runs, `engine._update_project_progress()` writes
`stages_completed` only when a stage is *approved* (`engine.py:343–350`).
A crash during the LLM call (before approval) therefore leaves:

- `state`: `DESIGN_APPROVED` (set at end of discovery, `pipeline_supervisor.py:372`)
- `current_sprint_number`: N (set by `set_current_sprint` at sprint start, `pipeline_supervisor.py:447`)
- `stages_completed`: does NOT include `BackendDeveloper`
- `completed_sprints`: does NOT include sprint N
- `failed_stage`: NOT set (only written on clean StageRunner exhaustion, `engine.py:357`)

**What files are on disk?**

Generated code files written by `WriteProjectFilesAction` are written with
plain `Path.write_text()` — no atomic rename. A crash mid-write leaves a
partial file on disk. `project.json` itself is safe (atomic rename).

**On restart: does PipelineSupervisor re-run BackendDeveloper?**

Yes. `_run_sprints` checks `completed_sprints` (`pipeline_supervisor.py:398`).
Sprint N is not there, so the full sprint re-runs including BackendDeveloper.

**Risk of partial file corruption?**

Yes. If `SprintDeltaPlanner` previously marked a file as `update` (patch
operation), `WriteProjectFilesAction` may apply a delta to a partially
written file rather than regenerating it from scratch, producing garbage
output.

**Verdict: PARTIAL** — `project.json` is safe; generated code files are NOT
atomically written and may be partially corrupt after a crash. The sprint
correctly re-runs, but re-execution may patch an already-broken file.

---

## Scenario 2: Crash After `mark_sprint_complete()` But Before `_run_sandbox()`

**Sequence in SprintExecutor.run() (sprint_executor.py:127–155):**

```
_run_sandbox_verification()   ← sandbox gate runs here (BEFORE mark_sprint_complete)
_run_sprint_deploy_and_review()
mark_sprint_complete()        ← sprint N added to completed_sprints
_run_sprint_validation()      (non-blocking)
return SprintResult(success=True)
```

**Sequence in PipelineSupervisor._run_sprints() (pipeline_supervisor.py:488–506):**

```
sprint_result = self._sprint_executor.run(...)   ← crash between here
_trigger_intelligence_index()
_pin_dependencies()
_run_sandbox()                ← ...and here
```

**After restart:**

`completed_sprints` includes sprint N (`mark_sprint_complete` already wrote
it). PipelineSupervisor reads `completed_sprints` at line 398, sees N, skips
sprint N entirely. `_run_sandbox()` for sprint N is never called on restart.

**Is sandbox verification bypassed?**

No. The verification GATE (`_run_sandbox_verification`) runs INSIDE
`SprintExecutor.run()` at `sprint_executor.py:131–144`, before
`mark_sprint_complete`. The code was verified before the sprint was marked
complete. PipelineSupervisor's `_run_sandbox()` is a secondary step that
loads the already-persisted result into `memory_manager` for BugAnalyst — it
is not the verification gate.

**What is lost?**

`memory_manager.store(project_id, "sandbox:latest", ...)` is never called
for sprint N (`pipeline_supervisor.py:928`). BugAnalyst reads from
`memory_manager` keyed `sandbox:latest`. On restart it will see stale or
missing sandbox data for sprint N, which may cause BugAnalyst to misidentify
bugs. The ArtifactStore entry (`sprint_N/sandbox_result`) IS present because
`SprintExecutor._persist_sandbox_result()` wrote it before the crash.

**Is this a correctness bug?**

No, for sprint completion semantics. The sprint was genuinely verified.
Minor data loss: `sandbox:latest` in memory will be stale/missing for
BugAnalyst context.

**Verdict: SAFE** for sprint state; PARTIAL for BugAnalyst context.

---

## Scenario 3: pip install Timeout Propagation

Step-by-step trace:

**`_run_subprocess()` — `code_sandbox.py:609–625`:**
```python
except subprocess.TimeoutExpired:
    return subprocess.CompletedProcess(
        cmd, returncode=124, stdout="", stderr="timeout after 60s"
    )
```
Returns a synthetic `CompletedProcess` with `returncode=124`. Never raises.

**`_install_python()` — `code_sandbox.py:316–331`:**
```python
proc = self._run_subprocess(cmd, cwd=project_dir)
if proc.returncode == 0:   # 124 ≠ 0, skipped
    ...
raw_errors = (proc.stderr or proc.stdout or "").splitlines()
# proc.stderr = "timeout after 60s"
# errors = ["timeout after 60s"]
return BuildResult(success=False, errors=["timeout after 60s"], ...)
```

**`install()` — `code_sandbox.py:281–287`:**
```python
return self._install_python(project_dir, started)
# → BuildResult(success=False, errors=["timeout after 60s"])
```

**`CodeSandbox.run()` — `code_sandbox.py:130–147`:**
```python
result.install = self.install(...)   # BuildResult(success=False)
if not result.install.success:       # True → enters branch
    result.build = BuildResult(success=False, errors=result.install.errors, ...)
    return result                    # SandboxResult with build.success=False
```

**`SprintExecutor._run_sandbox_verification()` — `sprint_executor.py:297–304`:**
```python
sandbox_result = self._code_sandbox.run(...)
if not sandbox_result.build.success:   # True
    errors = "; ".join(sandbox_result.build.errors[:3])
    # errors = "timeout after 60s"
    return False, "Build failed: timeout after 60s"
```

**`SprintExecutor.run()` — `sprint_executor.py:131–144`:**
```python
sandbox_success, sandbox_message = self._run_sandbox_verification(...)
# sandbox_success = False
if not sandbox_success:
    return SprintResult(
        sprint_complete=False, success=False,
        message="Sprint N build/test failed: Build failed: timeout after 60s"
    )
```

**Final verdict: CORRECT.** The pip install timeout propagates faithfully
through all five layers and surfaces as a sprint failure. No silent swallowing.

---

## Scenario 4: LLM Network Error in BackendDeveloperAgent

**Evidence — `stage_runner.py:146–170`:**
```python
try:
    exec_result = self.execution_manager.execute_stage(...)
    artifact = exec_result.artifact
    review_result = self.reviewer.review(artifact, ...)
except Exception as exc:
    last_error = f"{type(exc).__name__}: {exc}"
    logger.exception("stage attempt raised: ...")
    failed_approaches.append(last_error)
    attempt += 1
    continue   # ← triggers retry
```

Any exception from the LLM call (network error, timeout, API 5xx) is caught
at the StageRunner level, logged, and retried. After retries are exhausted:

**`stage_runner.py:252–259`:**
```python
return StageRunResult(success=False, message=message, ...)
```

**`engine.py:267–269`:**
```python
workflow.state = WorkflowState.Failed
self._update_project_failure(project_id, stage)
return WorkflowResult(workflow=workflow, success=False, message=result.message)
```

`WorkflowEngine.run()` catches the failure from StageRunner and returns
`WorkflowResult(success=False)`. The exception does NOT propagate.

**In PipelineSupervisor._run_stage_safe() — `pipeline_supervisor.py:949–981`:**
```python
try:
    result = self.engine.run(project_id, resolved_stage, request)
    ...
except Exception as exc:
    return _StageResult(success=False, message=f"{type(exc).__name__}: {exc}")
```

A second exception barrier exists at PipelineSupervisor. Even if WorkflowEngine
somehow raised (it doesn't), _run_stage_safe wraps it.

**Evidence: LLM network errors are fully contained. WorkflowEngine returns
WorkflowResult(success=False). The exception never reaches PipelineSupervisor.**

---

## Scenario 5: Bug-Fix Limit Hit With Broken Code

**`pipeline_supervisor.py:649–656`:**
```python
if bug_fix_iterations >= self._MAX_BUG_FIX_ITERATIONS:   # _MAX_BUG_FIX_ITERATIONS = 2
    logger.warning(
        "[PipelineSupervisor] BugAnalyst code_bug fix limit reached "
        "(%d/%d) — accepting current state and continuing to DEPLOYABLE."
        ...
    )
    # Do not apply another fix — let the loop finish naturally
```

When the limit is hit, the for-loop continues to the next release stage
(DevOps, Docs, Retro). When the for-loop finishes without a break:

**`pipeline_supervisor.py:732–733`:**
```python
logger.info("[PipelineSupervisor] Release phase complete, marking DEPLOYABLE")
self.workspace.update_state(project_id, ProjectState.DEPLOYABLE)
```

**End state: `DEPLOYABLE` — even with known broken code that BugAnalyst
confirmed it could not fix.**

**Is DEPLOYABLE correct here: NO.**

This is a correctness bug. The system has explicit evidence (BugAnalyst ran
twice, applied two fixes, build still failed) that the generated code is
broken, yet it marks the project `DEPLOYABLE`. A deployment of this artifact
will fail at runtime. The project should be marked `FAILED` or a new state
like `DEPLOYABLE_WITH_WARNINGS` with the bug report attached. At minimum,
`failed_stage` should be set so the API can surface the known failure to the
user.

---

## Scenario 6: Concurrent Change During Active Sprint

**Is SprintExecutor.run() in a thread?**

No. `PipelineSupervisor._run_sprints()` calls
`self._sprint_executor.run(project_id, sprint)` in a sequential for-loop
(`pipeline_supervisor.py:451`). No thread spawning at the sprint level.

**Is there locking on project.json?**

Yes, at the field-update level. `update_project_json` acquires a per-project
`threading.Lock` before every write (`workspace/manager.py:204–228`):
```python
lock = _get_project_lock(project_id)
with lock:
    data = self.load_project_json(project_id) or {...}
    data.update(updates)
    ...atomic rename...
```

**Can a concurrent API call corrupt project.json state?**

Yes, partially. The lock prevents torn writes (partial JSON) and ensures
atomic file replacement. However, the merge semantics are field-level
replacement, not list-merge. `data.update(updates)` replaces entire keys.

Example race:

- API call A calls `mark_sprint_complete(sprint=3)`: reads
  `completed_sprints=[1,2]`, computes `[1,2,3]`, queues
  `update_project_json({completed_sprints:[1,2,3]})`
- API call B calls some other state update concurrently: also reads then
  queues `update_project_json({completed_sprints:[1,2], ...other fields...})`

If B's write executes after A's inside the lock, `data.update({completed_sprints:[1,2]})` replaces A's `[1,2,3]` with `[1,2]` — sprint 3 disappears.

In practice, sprint execution is single-threaded, so this specific race only
materialises if a concurrent API endpoint (e.g. a user calling `/projects` or
a status update) happens to write `completed_sprints` simultaneously.
`mark_sprint_complete` and `set_current_sprint` both follow the unsafe
read-outside-lock / write-inside-lock pattern (`workspace/manager.py:273–313`).

**Verdict: PARTIAL** — torn writes are prevented; list-field overwrites from
concurrent writes that carry stale reads of array fields are not prevented.

---

## Idempotency Check

**Mechanism in `_run_discovery()` — `pipeline_supervisor.py:299–311`:**
```python
data = self.workspace.load_project_json(project_id) or {}
completed = set(data.get("stages_completed", []))

for stage_key in get_discovery_stages():
    from .stage_lookup import resolve_stage_name
    stage_value = resolve_stage_name(stage_key)
    if stage_value in completed:
        logger.debug("stage %s already completed, skipping", stage_key)
        continue
    ...run stage...
```

`stages_completed` is appended by `engine._update_project_progress()` at
`engine.py:343–350` every time a stage is approved.

If the pipeline restarts after completing 3 of 6 discovery stages:
`stages_completed` will contain the three resolved stage values. The loop
computes `stage_value = resolve_stage_name(stage_key)` for each stage and
skips any already in `completed`. Stage 4 is not in `completed`, so it runs.

**Mechanism in `_run_release()` — `pipeline_supervisor.py:553–557`:**
```python
while True:
    data = self.workspace.load_project_json(project_id) or {}
    completed = set(data.get("stages_completed", []))
    ...
    for stage_key in get_release_stages():
        stage_value = resolve_stage_name(stage_key)
        if stage_value in completed:
            continue
```

Release reloads `completed` on every while-loop iteration — stronger than
discovery's single read.

**Verdict: IDEMPOTENT.** Both phases correctly resume from the last
successfully completed stage on restart. Discovery reads `completed` once
(sufficient for sequential execution). Release re-reads on each BugFix loop
iteration (correct for the loop-restart pattern).

---

## CheckpointManager

**Implemented: YES (session/checkpoint.py) — but the ExecutionRecovery stub
is separate and NOT used.**

**Two systems exist:**

### 1. CheckpointManager (session/checkpoint.py) — FULLY IMPLEMENTED

SQLite-backed. Used by `CheckpointMiddleware` which is called from
`WorkflowEngine.run()` via the `_on_attempt` hook:

```python
# engine.py:212–216
def _on_attempt(attempt, artifact, review_result):
    self._checkpoint.save(
        session_id, stage_name, project_id, attempt, [], ""
    )
```

Each LLM attempt saves a `SessionCheckpoint` row. On clean success, the
checkpoint is deleted (`engine.py:225`). A checkpoint that survives process
death marks the session as incomplete and is reported at next startup
(`CheckpointMiddleware.report_incomplete()` called in `WorkflowEngine.__init__`
at `engine.py:165`).

The checkpoint contains: `session_id`, `stage`, `project_id`,
`attempt_number`, `failed_approaches`, `last_artifact_summary`.

**What it does NOT do:** it does not automatically re-run the incomplete
stage. It only logs a warning listing orphaned checkpoints. The pipeline
resumes by re-reading `stages_completed` from `project.json` — if the stage
was not approved, it re-runs it from attempt 0 (not from the saved attempt).
The checkpoint data is therefore informational only; `failed_approaches` from
the previous run is NOT fed back into the retry context on resume.

### 2. ExecutionRecovery.create_checkpoint() (execution/execution_recovery.py) — STUB

```python
def create_checkpoint(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
    return checkpoint   # ← does nothing, returns input unchanged
```

No persistence. The `RecoveryCheckpoint` dataclass is a plain in-memory
object. This class is NOT called anywhere in the main pipeline.

**What is lost on crash:**

- The partial LLM response from the in-progress attempt (always lost — no
  streaming persistence).
- The `failed_approaches` list from the crashed run (not restored on resume).
- The current retry attempt number (always restarts from attempt 0).
- Any generated code files that were being written mid-operation (plain
  `write_text`, not atomic).

---

## State Transitions on Failure

| Failure type | State set in project.json | Allows retry on restart | Evidence |
|---|---|---|---|
| Discovery stage fails (engine returns success=False) | Unchanged from last successful state; `failed_stage` written by `engine._update_project_failure()` | Yes — state still in `DISCOVERY_STATES`, discovery re-runs | `pipeline_supervisor.py:326–333`, `engine.py:355–357` |
| Discovery stage crashes (Python exception) | Unchanged (no state write) | Yes — same as above | `pipeline_supervisor.py:206–224` outer try/except returns PipelineResult without writing state |
| Sprint failure (SprintExecutor returns success=False) | NOT updated — remains `DESIGN_APPROVED` or `SPRINT_IN_PROGRESS` (quick mode) | Yes — state in SPRINT_STATES or == DESIGN_APPROVED, _run_sprints re-enters | `pipeline_supervisor.py:473–486` |
| Sprint crash (Python exception mid-sprint) | NOT updated; `completed_sprints` does not include sprint N | Yes — same resume path | `pipeline_supervisor.py:206–224` |
| Release stage fails | NOT updated (non-fatal, loop continues) | N/A — release failures are non-fatal and the loop advances | `pipeline_supervisor.py:580–585` |
| BugAnalyst fix limit reached | Set to `DEPLOYABLE` even with known broken code | No — DEPLOYABLE is terminal | `pipeline_supervisor.py:732–733` |
| Process crash after `mark_sprint_complete` | Sprint N in `completed_sprints`, state unchanged | Partial — sprint N skipped; `_run_sandbox()` not called; memory_manager loses sandbox:latest | `sprint_executor.py:147`, `workspace/manager.py:295–314` |
| SPRINT_BLOCKED | Never explicitly set by `_run_sprints()` on failure | N/A — dead state code (in enum and SPRINT_STATES set, never written by pipeline) | `pipeline_supervisor.py:72`, no `update_state(SPRINT_BLOCKED)` anywhere in file |

---

## Recovery Verdict

**What recovers automatically:**

- Any discovery stage that failed or crashed: pipeline reads `stages_completed`,
  sees the stage missing, re-runs it. Full automatic recovery.
- Any sprint that failed before `mark_sprint_complete`: sprint not in
  `completed_sprints`, pipeline re-runs the full sprint. Full automatic recovery.
- Any release stage that failed: non-fatal, pipeline continues to next stage.
- `project.json` itself: atomic writes prevent corruption. Never partial.
- Concurrent write torn state: lock prevents torn JSON; list-field races
  are mitigated because sprint execution is single-threaded.

**What is permanently lost after crash:**

1. **Generated code files mid-write**: `WriteProjectFilesAction` uses plain
   `Path.write_text()`. A crash during a file write leaves the file truncated
   or empty. On restart, `SprintDeltaPlanner` may issue a `patch` operation
   against the broken file rather than a full regeneration.

2. **LLM attempt progress**: the CheckpointManager saves that an attempt was
   in-progress but does NOT replay it. The stage restarts from attempt 0.
   All `failed_approaches` context from the crashed run is lost.

3. **`sandbox:latest` in memory_manager**: if crash occurs between
   `mark_sprint_complete()` and `PipelineSupervisor._run_sandbox()`, the
   ArtifactStore entry exists but `memory_manager.store("sandbox:latest")`
   was never called. BugAnalyst may receive stale or absent sandbox context.

4. **`SPRINT_BLOCKED` state**: never written. If a sprint fails, there is no
   way to distinguish "sprint in progress" from "sprint failed" by reading
   state alone. The only reliable indicator is whether sprint N is absent from
   `completed_sprints`.

---

## Critical Bugs (Numbered)

1. **DEPLOYABLE with known broken code** (`pipeline_supervisor.py:732–733`):
   When `_MAX_BUG_FIX_ITERATIONS` (2) is exhausted and build still fails,
   the project is marked `DEPLOYABLE`. State should be `FAILED` or equivalent.
   A deployed artifact from this path will fail at runtime.

2. **Generated code files not atomically written**: `WriteProjectFilesAction`
   writes files with `Path.write_text()`. A crash mid-write leaves a partial
   file. On restart, `SprintDeltaPlanner` patch mode may corrupt the file
   further. Fix: write to a temp file and rename, same pattern as
   `update_project_json`.

3. **CheckpointManager saves checkpoints but never restores them for retry
   context** (`engine.py:212–216`, `session/checkpoint.py:105–115`): The
   checkpoint is reported as incomplete on restart but the `failed_approaches`
   and `attempt_number` are never fed back into the new StageRunner run. The
   crash-recovery checkpoint system is informational only.

4. **`ExecutionRecovery.create_checkpoint()` is a stub**
   (`execution/execution_recovery.py:16–18`): Returns the checkpoint unchanged
   without persisting it. Any caller that depends on `ExecutionRecovery` for
   durability gets a no-op. (Currently no production code path calls it, but
   it is a public API that misleads future callers.)

5. **`SPRINT_BLOCKED` state is dead code** (`pipeline_supervisor.py:72`):
   It appears in `SPRINT_STATES` (so restart correctly re-enters
   `_run_sprints`) but is never explicitly set by `_run_sprints()` on sprint
   failure. No external caller sets it either (no `update_state(SPRINT_BLOCKED)`
   call anywhere in the codebase). The state is unreachable via the pipeline.

6. **`mark_sprint_complete` and `set_current_sprint` read outside the lock**
   (`workspace/manager.py:273–313`): Both methods call
   `load_project_json()` before entering `update_project_json()`. A
   concurrent write between the outer read and the inner re-read can silently
   overwrite list fields (`completed_sprints`, `sprint_plan`) with stale
   values. Sprint execution is currently single-threaded so this race is low
   probability, but an API endpoint that writes `completed_sprints`
   concurrently could lose a sprint completion record.

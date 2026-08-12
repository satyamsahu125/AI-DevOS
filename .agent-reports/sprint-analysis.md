# Sprint Pipeline Analysis

---

## Post-Implementation Gap: What Happens After Code Generation

**Finding:** After BackendDeveloper and FrontendDeveloper stages complete inside `SprintExecutor.run()`, there is zero call to CodeSandbox, install, build, or any test runner. The executor runs SprintDeploy and SprintReview (both LLM agents, not real execution), marks the sprint complete, and returns. The CodeSandbox is invoked only later, in `PipelineSupervisor._run_sprints()` — after `SprintResult.success=True` is already returned and `mark_sprint_complete` has already been called.

**Evidence (SprintExecutor.run, lines 119–133):**
```python
# ── Step 3: BackendDeveloper ─────────────────────────────────
backend_result = self._run_engine_stage(project_id, "BackendDeveloper", plan_context)

# ── Step 4: FrontendDeveloper ────────────────────────────────
frontend_result = self._run_engine_stage(project_id, "FrontendDeveloper", plan_context)

all_success = backend_result.success and frontend_result.success

if all_success:
    self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
    self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
    self._run_sprint_validation(project_id, sprint)

return SprintResult(
    sprint_complete=all_success,
    all_sprints_complete=False,
    success=all_success,
    message="Sprint completed" if all_success else "Sprint execution failed",
)
```

**Evidence (PipelineSupervisor._run_sprints, lines 451–506):**
```python
sprint_result = self._sprint_executor.run(project_id, sprint)   # ← mark_sprint_complete already called inside

# ... syntax check only if _code_sandbox is not None ...

# R2: Pin dependencies...
self._pin_dependencies(project_id, sprint_number=n)
# Phase 5: run code execution sandbox ...
self._run_sandbox(project_id, sprint_number=n)   # NON-BLOCKING — exceptions caught; sprint is ALREADY marked complete
```

**File:** `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py` (executor) and `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py` (post-sprint calls)

**Function:** `SprintExecutor.run()` / `PipelineSupervisor._run_sprints()`

**Impact:** A sprint can succeed and be marked complete with no package installation, no build, and no tests ever executed. `SprintDeploy` and `SprintReview` are LLM agents (they review the generated code text), not actual build/test runners. The sandbox is fired afterward as a non-blocking side-effect whose failure does NOT roll back sprint completion.

**Recommendation:** Run `CodeSandbox.run()` synchronously inside `_run_sprints()`, before calling `mark_sprint_complete`, and gate the sprint-complete mark on `sandbox_result.build.success`.

**Confidence:** High

---

## SprintResult Fields

**File:** `F:\AI-DevOS3\backend\app\shared\models\sprint.py` (lines 59–63)

```python
class SprintResult(BaseModel):
    all_sprints_complete: bool = False
    sprint_complete: bool = False
    success: bool = True          # ← defaults to True — a default-constructed SprintResult looks like success
    message: str = ""
```

**Fields (all four):**
| Field | Type | Default |
|---|---|---|
| `all_sprints_complete` | bool | False |
| `sprint_complete` | bool | False |
| `success` | bool | **True** |
| `message` | str | "" |

**Critical observation:** `success` defaults to `True`. A bare `SprintResult()` with no arguments is indistinguishable from a successful result. Any code path that constructs `SprintResult()` without explicitly setting `success=False` will silently report success. In practice `SprintExecutor.run()` always sets `success=all_success` explicitly, so this is a latent trap rather than an active bug today — but any future early-return path that forgets to pass `success=False` will create a false positive.

**Confidence:** High

---

## ProjectState — Declared vs Actually Used

**File:** `F:\AI-DevOS3\backend\app\shared\enums\project_state.py`

**All declared states (23 total):**
`EMPTY`, `CLARIFYING`, `QA_PENDING`, `QA_IN_PROGRESS`, `QA_COMPLETE`, `REQUIREMENTS_READY`, `ARCHITECTURE_READY`, `DESIGN_READY`, `ARCHITECTURE_REVIEW_PENDING`, `DESIGN_REVIEW_PENDING`, `SPRINT_PLAN_REVIEW_PENDING`, `DESIGN_APPROVED`, `SPRINT_PLAN_READY`, `SPRINT_IN_PROGRESS`, `SPRINT_COMPLETE`, `SPRINT_BLOCKED`, `ALL_SPRINTS_COMPLETE`, `AWAITING_HUMAN_APPROVAL`, `CHANGE_REQUESTED`, `IMPACT_ANALYZED`, `REPLANNING`, `RESUMING_FROM_CHANGE`, `DEPLOYABLE`, `DONE`, `FAILED`, `PAUSED`

**States actually assigned (via `workspace.update_state` or direct construction) in the two files:**

| State | Where assigned |
|---|---|
| `ARCHITECTURE_REVIEW_PENDING` | PipelineSupervisor._run_discovery (line 339) |
| `DESIGN_REVIEW_PENDING` | PipelineSupervisor._run_discovery (line 357) |
| `DESIGN_APPROVED` | PipelineSupervisor._run_discovery (line 372) |
| `SPRINT_IN_PROGRESS` | PipelineSupervisor._run_sprints (line 406, quick mode only) |
| `ALL_SPRINTS_COMPLETE` | PipelineSupervisor._run_sprints (lines 422, 509) |
| `RESUMING_FROM_CHANGE` | PipelineSupervisor._run_release (lines 639, 644) |
| `DEPLOYABLE` | PipelineSupervisor._run_release (line 692) |
| `FAILED` | PipelineSupervisor.run() exception handler (line 216) |

**States NEVER assigned in either file (dead states):**

| State | Notes |
|---|---|
| `SPRINT_BLOCKED` | Listed in `SPRINT_STATES` routing set (line 73) and mentioned in docstring, but never assigned anywhere in either file. The retry-limit path that should transition to this state does not exist. |
| `SPRINT_COMPLETE` | Declared but never transitioned to; individual sprint completion is tracked via `mark_sprint_complete()` on the workspace, not via a state enum value. |
| `DONE` | Checked as a terminal condition (line 279: `state in [ProjectState.DEPLOYABLE, ProjectState.DONE]`) but never assigned. |
| `PAUSED` | Never assigned. |
| `AWAITING_HUMAN_APPROVAL` | Never assigned. |
| `CHANGE_REQUESTED` | Never assigned. |
| `IMPACT_ANALYZED` | Never assigned. |
| `REPLANNING` | Never assigned. |
| `QA_COMPLETE` | Listed in `RELEASE_STATES` routing set (line 78) but the pipeline never reaches it through a state assignment; `ALL_SPRINTS_COMPLETE` is the actual entry point to the release phase. |

**Most impactful dead state:** `SPRINT_BLOCKED`. It sits in the routing set that determines pipeline phase, implying a blocked-sprint state machine transition, but it is never written. If a sprint exceeds retry limits (handled in PipelineSupervisor by returning `success=False`), the project stays in `SPRINT_IN_PROGRESS` state (or whatever state it was in before) — it never transitions to `SPRINT_BLOCKED`. There is no code path that creates the intended human-intervention pause for sprint failures.

**Confidence:** High

---

## Bug-Fix Loop — Current Mechanics

**File:** `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`

**Max iterations:**
```python
_MAX_BUG_FIX_ITERATIONS = 2      # line 523 — code_bug fixes
_MAX_ARCH_ROLLBACK_ITERATIONS = 2 # line 529 — spec_bug / architecture_bug rollbacks
```

**Loop structure (lines 553–688):** A `while True:` loop wraps an inner `for stage_key in get_release_stages():` loop. The inner loop runs all release stages. When BugAnalyst outputs a `code_bug`:
1. `bug_fix_iterations` is incremented.
2. The affected backend or frontend stage is re-run directly via `engine.run()` (no SprintExecutor, no file planning).
3. QA and BugAnalyst entries are cleared from `stages_completed` so they re-run.
4. `restart_from_qa = True` + `break` exits the inner for-loop.
5. The `while True` loop continues from the top, reloading `stages_completed` and re-running release stages from QA onwards.

When `bug_fix_iterations >= _MAX_BUG_FIX_ITERATIONS`, the fix is skipped and the loop finishes naturally — the project is marked `DEPLOYABLE` despite unfixed bugs.

**Does the bug-fix loop invoke CodeSandbox?** No — not directly. The sandbox was run (non-blocking) after each sprint in `_run_sprints()`. BugAnalyst reads sandbox results from memory (`sandbox:latest`) but the fix loop itself does not re-run the sandbox. After a code_bug fix in the release phase, the code is changed but the sandbox is not re-executed; BugAnalyst in the next iteration reads stale sandbox results.

**Evidence (lines 648–684):**
```python
elif bug_type == "code_bug":
    if bug_fix_iterations >= self._MAX_BUG_FIX_ITERATIONS:
        # ... accepts current state, advances to DEPLOYABLE
    else:
        bug_fix_iterations += 1
        ...
        self.engine.run(project_id, _resolve(target_stage), fix_content)  # re-run backend/frontend
        # clears QA+BugAnalyst from completed
        restart_from_qa = True
        break
```

**Confidence:** High

---

## Sprint Failure Propagation

**Finding:** Sprint failure propagates correctly from SprintExecutor to PipelineSupervisor, but only for FileStructurePlanner failure and combined BackendDev+FrontendDev failure. Individual stage failures (one of backend or frontend succeeds, the other fails) produce `all_success=False` and a failed SprintResult.

**Exact code path:**

In `SprintExecutor.run()`:

```python
# lines 101–107 — FileStructurePlanner failure → immediate return
plan_result = self._run_file_planner(project_id, plan_context)
if not plan_result.success:
    return SprintResult(
        sprint_complete=False,
        success=False,
        message=plan_result.message,
    )

# lines 116–133 — Backend/Frontend failure → all_success=False
backend_result = self._run_engine_stage(project_id, "BackendDeveloper", plan_context)
frontend_result = self._run_engine_stage(project_id, "FrontendDeveloper", plan_context)
all_success = backend_result.success and frontend_result.success
if all_success:
    self._run_sprint_deploy_and_review(...)
    self._workspace.mark_sprint_complete(...)
    self._run_sprint_validation(...)
return SprintResult(
    sprint_complete=all_success,
    success=all_success,
    message="Sprint completed" if all_success else "Sprint execution failed",
)
```

In `PipelineSupervisor._run_sprints()`:

```python
# lines 473–486 — failed SprintResult stops the pipeline
if not sprint_result.success:
    logger.error(...)
    return PipelineResult(
        project_id=project_id,
        state=self.workspace.get_state(project_id),
        success=False,
        message=f"Sprint {n} failed: {sprint_result.message}",
        failed_stage=f"sprint_{n}",
        current_sprint=n,
        completed_stages=list(data.get("stages_completed", [])),
    )
```

**Gap:** ScrumMaster failure (lines 162–180) and SprintDeltaPlanner failure (lines 190–211) are explicitly non-blocking — logged as warnings, sprint continues regardless. SprintDeploy/SprintReview failure (lines 231–257) is also non-blocking (wrapped in try/except, logged as warning). So the sprint can be marked complete even if deploy simulation or review fail.

**Confidence:** High

---

## Insertion Point for install → build → test

**Finding:** The minimum-impact insertion point is in `PipelineSupervisor._run_sprints()`, between the successful `sprint_result` check and the existing `_run_sandbox()` call — but crucially `mark_sprint_complete` has already been called inside `SprintExecutor.run()`. To make the sandbox result gate the increment, one of two things must change:

**Option A — Move sandbox call inside SprintExecutor (cleanest isolation):**

Insert a synchronous sandbox call in `SprintExecutor.run()` at line 125, between `_run_sprint_deploy_and_review()` and `mark_sprint_complete()`:

```python
# CURRENT (lines 123–126 of sprint_executor.py):
if all_success:
    self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
    self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
    self._run_sprint_validation(project_id, sprint)

# PROPOSED:
if all_success:
    self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
    # ← INSERT: sandbox.install() + sandbox.run() → check build.success
    # Only mark_sprint_complete if build passes
    if sandbox_result.build.success:
        self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
    else:
        all_success = False   # propagate failure back to PipelineSupervisor
    self._run_sprint_validation(project_id, sprint)
```

SprintExecutor would need `_code_sandbox` wired through its constructor (currently absent).

**Option B — Block completion in PipelineSupervisor (no SprintExecutor changes):**

In `PipelineSupervisor._run_sprints()`, after `sprint_result.success` is True but BEFORE the `completed_sprints` update, run the sandbox synchronously and gate on build success. `mark_sprint_complete` would need to be called from PipelineSupervisor rather than SprintExecutor (currently a layering violation since SprintExecutor calls it first).

**Evidence — current PipelineSupervisor ordering (lines 455–506):**
```python
sprint_result = self._sprint_executor.run(project_id, sprint)
# ↑ mark_sprint_complete already called inside here ↑

if sprint_result.success and self._code_sandbox is not None:
    syntax_errors = self._code_sandbox.syntax_check(project_id, sprint=n)   # only syntax
    # no build or test check here

if not sprint_result.success:
    return PipelineResult(...)                  # failure exit

# ... intelligence index, pin deps ...
self._run_sandbox(project_id, sprint_number=n)  # non-blocking, result ignored for gating
```

**Minimum code change (Option A):**
1. `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`, `SprintExecutor.__init__()`: add `code_sandbox=None` parameter and store as `self._code_sandbox`.
2. `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`, `SprintExecutor.run()`, line 125: insert synchronous `self._code_sandbox.run()` call and check `build.success` before calling `mark_sprint_complete`.
3. `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`, `SprintResult` return (line 128–133): return `success=False` if sandbox build failed.
4. Wire `code_sandbox` into `SprintExecutor` at construction site (wherever SprintExecutor is instantiated).

**Confidence:** High

---

## Sprint ↔ Release Loop Interaction

**Finding:** The sprint loop (`_run_sprints`) and the release loop (`_run_release`) are completely sequential and share no feedback path. `_run_release` never calls `SprintExecutor`. The BugAnalyst code-fix path in `_run_release` calls `engine.run()` directly for backend/frontend stages, completely bypassing SprintExecutor's file planning, sprint context assembly, and sprint marking machinery.

**Evidence (PipelineSupervisor._run_impl, lines 264–272):**
```python
if state in SPRINT_STATES or state == ProjectState.DESIGN_APPROVED:
    result = self._run_sprints(project_id, request)
    if not result.success:
        return result
    state = self.workspace.get_state(project_id)    # ← must be ALL_SPRINTS_COMPLETE

if state in RELEASE_STATES or state == ProjectState.ALL_SPRINTS_COMPLETE:
    result = self._run_release(project_id, request)
    return result
```

**Evidence (BugAnalyst fix path, lines 666–668):**
```python
fix_content = f"A bug was found. Your task is to apply the following fix: {fix}"
from .stage_lookup import resolve_stage_name as _resolve
self.engine.run(project_id, _resolve(target_stage), fix_content)
# ← No SprintExecutor, no FileStructurePlanner, no sprint context, no sandbox re-run
```

**Implication:** Code fixes applied during the release phase:
- Do not re-run `FileStructurePlanner` (may write files outside the planned structure)
- Do not re-run `SprintDeltaPlanner` (no diff-awareness for the fix)
- Do not re-run the sandbox (BugAnalyst reads stale results in subsequent iterations)
- Do not create a git commit for the fix (no `_commit_sprint_to_git` equivalent)
- Do not update `mark_sprint_complete` (sprint history is unaffected)

**Confidence:** High

---

## Summary: Minimum Changes for Verified Increment

Ordered by dependency (earlier items must land before later ones):

1. **Wire `code_sandbox` into `SprintExecutor`**
   File: `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`
   Function: `SprintExecutor.__init__()`
   Change: Add `code_sandbox=None` parameter; store as `self._code_sandbox`.
   Also update the construction site wherever `SprintExecutor(...)` is instantiated, passing the same `code_sandbox` that `PipelineSupervisor` already holds.

2. **Run install + build + test synchronously before `mark_sprint_complete`**
   File: `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`
   Function: `SprintExecutor.run()`, between lines 124–125 (after `_run_sprint_deploy_and_review`, before `mark_sprint_complete`)
   Change: Call `self._code_sandbox.install(project_id)` then `self._code_sandbox.run(project_id, sprint=sprint.sprint_number)`. Check `sandbox_result.build.success`. If False, set `all_success = False` (do not call `mark_sprint_complete`, do not call `_run_sprint_validation`).

3. **Return `success=False` from `SprintExecutor.run()` when sandbox fails**
   File: `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py`
   Function: `SprintExecutor.run()`, line 128–133 (the return statement)
   Change: Already correctly uses `all_success` in the return — no change needed IF step 2 correctly sets `all_success = False` on sandbox failure.

4. **Remove duplicate `_run_sandbox` call in `PipelineSupervisor`** (or demote to memory-only storage)
   File: `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`
   Function: `PipelineSupervisor._run_sprints()`, line 500
   Change: Either remove `self._run_sandbox(...)` (sandbox was already run in step 2) or keep it only to store results to memory for BugAnalyst (convert from re-running to re-loading). This avoids running the sandbox twice per sprint.

5. **Re-run sandbox after BugAnalyst code fixes in the release loop**
   File: `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`
   Function: `PipelineSupervisor._run_release()`, after `self.engine.run(project_id, _resolve(target_stage), fix_content)` (lines 668)
   Change: Add a `self._run_sandbox(project_id)` call (non-blocking is acceptable here) so BugAnalyst in the next iteration reads fresh results rather than stale sprint-time results.

6. **Assign `ProjectState.SPRINT_BLOCKED` when a sprint fails**
   File: `F:\AI-DevOS3\backend\app\workflow\pipeline_supervisor.py`
   Function: `PipelineSupervisor._run_sprints()`, the `if not sprint_result.success:` block (lines 473–486)
   Change: Before returning the failed `PipelineResult`, call `self.workspace.update_state(project_id, ProjectState.SPRINT_BLOCKED)`. This makes the state machine honest — currently the project is left in `SPRINT_IN_PROGRESS` (or prior state) forever on sprint failure, with no way for the UI to distinguish an in-progress sprint from a blocked one.

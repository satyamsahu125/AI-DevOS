# Audit 5: Change and Replanning Architecture

---

## ChangeManager

**Exists: YES**

**Evidence:** `F:\AI-DevOS3\backend\app\workflow\change_manager.py`

**What it does:**

- `submit(project_id, change_description)` — calls `ImpactAnalyzer.analyze()` to classify the change and compute which stages need re-running. Optionally calls `analyze_file_impact()` if code stages are already completed. Writes `pending_change` dict to `project.json` containing `change_id`, `description`, `affected_stages`, `safe_stages`, `analyzed_at`. Transitions state to `CHANGE_REQUESTED` and broadcasts `change_analyzed` event.
- `apply(project_id, change_id, confirmed, user_comment)` — if `confirmed=True`, removes all affected stages from `stages_completed` (leaving only `safe_stages`), appends a record to `requirement_changes[]` in `project.json`, sets `current_stage` to the first affected stage, and transitions to `RESUMING_FROM_CHANGE`. If `confirmed=False`, clears `pending_change` and reverts to `SPRINT_IN_PROGRESS`.

**What it cannot do:**

- Does NOT delete or remove any files from disk.
- Does NOT create new sprint tasks for added features.
- Does NOT know which sprint number implemented a given piece of functionality — impact is stage-level only, not sprint-level.
- Does NOT auto-resume the pipeline after `apply()`. The caller must separately trigger `/workflow/{id}/continue`.
- Does NOT interrupt an actively running sprint executor. A change can be submitted while a sprint is running; it lands as `pending_change` in `project.json` and sits there until the sprint finishes and the user confirms it.

---

## ImpactAnalyzer

**Exists: YES**

**Evidence:** `F:\AI-DevOS3\backend\app\workflow\impact_analyzer.py`

**What it does:**

`analyze()`:
1. Uses an LLM call to classify the change into one of 7 change types (`add_feature`, `remove_feature`, `modify_ui`, `modify_api`, `modify_database`, `modify_auth`, `change_scale`).
2. Looks up directly affected stages from a static `CHANGE_TYPE_IMPACT` dict.
3. Propagates impact downstream using a static `STAGE_DEPENDENCIES` DAG.
4. Returns an `ImpactAnalysis` object with: `affected_stages`, `safe_stages`, `affected_files` (pulled from artifact `planned_paths`), `sprints_to_replan` (always `[1]` if code stages are touched, `[]` otherwise — this is hardcoded, not computed).

`analyze_file_impact()` (called when code stages are already complete):
- Uses `CodeSummarizer.get_relevant_files()` + `DependencyGraph.get_impact()` to identify specific files to regenerate.
- Returns a dict with `files_to_regenerate` and `files_safe`.
- Requires all three intelligence-layer components (`file_indexer`, `dep_graph`, `code_summarizer`) to be wired; if any is `None`, returns empty lists with a "not available" explanation.

**What it cannot do:**

- Does NOT produce a structured list of affected test files.
- Does NOT identify which sprint numbers are affected beyond the hardcoded `[1]`.
- Does NOT identify specific sprint tasks or backlog items that need regeneration.
- `sprints_to_replan` is `[1]` for any code-touching change regardless of whether the project has 1 or 5 sprints.

---

## Scenario 1: Add Feature

**User submits: "Add payroll module" after Sprint 1 completes.**

**API endpoint exists:** YES — `POST /workflow/{project_id}/change`

**Creates a change record:** YES — `pending_change` in `project.json`, and after confirmation, appended to `requirement_changes[]`.

**Identifies affected sprints/files:** PARTIAL — ImpactAnalyzer classifies as `add_feature`, maps to affected stages `[product_owner, architect, sprint_planner, scrum_master, file_planner, backend, frontend, qa, document]`, identifies files from existing artifact `planned_paths` (up to 20 per stage), but `sprints_to_replan` is always hardcoded to `[1]`.

**Creates new sprint tasks:** NO — `apply()` removes affected stages from `stages_completed` so the pipeline re-runs those stages. The sprint planner stage will re-execute when the pipeline resumes, which will regenerate the sprint plan including the new feature. But there is no dedicated "add sprint task" step — it relies on full stage re-runs.

**Pipeline resumes correctly after confirm:** NO (CRITICAL GAP) — After `apply()`, state becomes `RESUMING_FROM_CHANGE`. When the user calls `/workflow/{id}/continue`, `WorkflowManager.run()` passes control to `PipelineSupervisor._run_impl()`. `RESUMING_FROM_CHANGE` is not a member of `DISCOVERY_STATES`, `SPRINT_STATES`, or `RELEASE_STATES` in `pipeline_supervisor.py`. The supervisor falls through to the "Terminal states" block and returns `success=False` with message "Pipeline in state: resuming_from_change". The pipeline does not restart.

**Verdict: PARTIAL**

What works: API exists, analysis classifies correctly, affected stages are computed, change record is written.

What is missing: Pipeline does not resume after apply() because `RESUMING_FROM_CHANGE` is not handled in `PipelineSupervisor._run_impl()`. No sprint-task-level granularity. No auto-resume after confirmation.

---

## Scenario 2: Modify Feature

**User submits: "Change authentication from JWT to OAuth" during Sprint 2.**

**API endpoint exists:** YES.

**Creates a change record:** YES.

**Identifies affected stages:** YES — `modify_auth` maps to `[architect, security, file_planner, backend, frontend, qa]`. Downstream propagation adds any stage that depends on these.

**Identifies files:** PARTIAL — only if intelligence layer (FileIndexer + DependencyGraph + CodeSummarizer) is wired. If not, `analyze_file_impact()` returns empty.

**Pipeline resumes correctly:** NO — same RESUMING_FROM_CHANGE gap as Scenario 1.

**While sprint is active:** The change is accepted and creates `pending_change` in `project.json`. The active Sprint 2 executor continues running uninterrupted. There is no mechanism to inject the change into the running sprint. Only after the sprint naturally finishes (or is stopped via `/workflow/{id}/stop`) can the user confirm the change.

**Verdict: PARTIAL**

What works: Analysis, classification, change record, API.

What is missing: Active sprint interrupt, pipeline re-resume after confirmation.

---

## Scenario 3: Remove Feature

**User submits: "Remove the payroll module" after Sprint 2.**

**Creates change record:** YES.

**Identifies affected stages:** YES — `remove_feature` maps to `[product_owner, architect, file_planner, backend, frontend, qa, document]`. These stages will re-run, generating new artifacts that no longer include payroll.

**Deletes payroll files from disk:** NO — there is no file deletion anywhere in the change pipeline. `analyze_file_impact()` returns a list of `files_to_regenerate` but these are only regenerated if those stages re-run the file-writing agents. Orphaned files that existed in prior sprints remain on disk.

**Removes payroll from sprint plan:** NO direct removal — the sprint planner stage re-runs and produces a new plan, but old sprint artifacts (sprint_1/sprint_plan.json, etc.) remain. The new plan simply omits payroll. Files written in the old sprint that implement payroll are not removed.

**Verdict: PARTIAL**

What works: Impact analysis classifies correctly, stages identified, change record written.

What is missing: No file deletion. No artifact cleanup for prior sprints. Orphaned files remain in the workspace after a remove_feature change.

---

## Scenario 4: Change an Already-Completed Sprint

**Sprint 1 is complete. User says "Actually Sprint 1 should use SQLite not PostgreSQL."**

**System knows Sprint 1 is complete:** YES — `completed_sprints` is tracked in `project.json`.

**System knows which files implement the database layer:** PARTIAL — only if the intelligence layer is wired (`file_indexer`, `dep_graph`, `code_summarizer`). If not wired, `analyze_file_impact()` returns empty.

**Identifies what needs to change:** PARTIAL — ImpactAnalyzer classifies as `modify_database`, maps to `[architect, file_planner, backend, qa]`. These stages will be marked for re-run. But the system does not know that "Sprint 1 = PostgreSQL files" specifically; it only knows which stages are affected.

**Replans correctly:** NO — same RESUMING_FROM_CHANGE gap. Also, `sprints_to_replan` is always hardcoded to `[1]`; if Sprint 1 is actually sprint number 2, this field is wrong.

**Does state guard against re-running a completed sprint's artifacts without acknowledgment:** YES — `apply()` explicitly requires user confirmation (`confirmed=True`) before removing stages from `stages_completed`.

**Verdict: PARTIAL**

What works: State tracking, user confirmation gate, impact classification.

What is missing: Pipeline resume failure (RESUMING_FROM_CHANGE gap), no sprint-number-aware replanning, hardcoded `sprints_to_replan=[1]`, no file-level guidance without intelligence layer wired.

---

## Scenario 5: Change During Active Sprint

**Sprint 2 is running (SprintExecutor.run() is executing). User sends a change.**

**Interrupt mechanism:** None. There is no mechanism to interrupt a running `SprintExecutor`. The sprint executor runs to completion (or retry-limit failure) regardless of any change submitted.

**Is the change queued:** NO — `submit()` writes `pending_change` immediately to `project.json`. The running sprint is unaware of it (it does not read `pending_change`).

**Is the change ignored:** NO — it is accepted by the API and stored in `project.json`.

**Is the change applied immediately:** NO — `apply()` has not been called; the change sits as `pending_change` until the user explicitly calls `/workflow/{id}/change/confirm`.

**Stop mechanism:** The user can call `POST /workflow/{id}/stop`, which sets a stop flag. `stage_runner.py` checks `execution_state.is_stop_requested(project_id)` between stage retry attempts. This will pause the sprint at its next retry checkpoint, not immediately.

**Verdict: PARTIAL**

What works: Change is accepted, stored, and analyzed. User can stop the sprint via /stop.

What is missing: No mid-sprint interrupt. No change queue with ordering guarantees. No notification to the running executor that a change is pending. User must manually stop, confirm, then resume.

---

## Rollback (spec_bug / architecture_bug)

**What it actually does:**

When `BugAnalystAgent.analyse()` classifies a QA failure as `spec_bug` or `architecture_bug`, `PipelineSupervisor._run_release()` (lines 603–646) calls:

1. `change_manager.submit(project_id, change_description=f"BugAnalyst detected {bug_type}: {fix_instruction}")` — this triggers a full `ImpactAnalysis` which classifies the fix instruction as a new change type (usually `add_feature` fallback), marks affected stages for re-run.
2. `change_manager.apply(project_id, change_id, confirmed=True)` — immediately applies without user confirmation, removing affected stages from `stages_completed` and transitioning to `RESUMING_FROM_CHANGE`.
3. Returns a `PipelineResult(state=RESUMING_FROM_CHANGE, success=True)` and exits `_run_release()`.

**What "rollback" does NOT do:**

- Does NOT revert any files to a prior state.
- Does NOT git-checkout any prior commit.
- Does NOT reset sprint state (sprint counters, sprint artifacts remain).
- Does NOT re-run anything automatically. It exits the current pipeline loop and requires the caller to restart.

**Guard against infinite loops:** `_MAX_ARCH_ROLLBACK_ITERATIONS = 2`. After 2 rollbacks, the system logs a warning and falls through to continue toward DEPLOYABLE without another rollback.

**The pipeline-resume gap also applies here:** After the BugAnalyst rollback exits `_run_release()`, the state is `RESUMING_FROM_CHANGE`. The background thread exits. A human (or monitoring system) must call `/workflow/{id}/continue` to resume, and that call will hit the same RESUMING_FROM_CHANGE gap in `PipelineSupervisor._run_impl()`.

**Evidence:** `pipeline_supervisor.py` lines 599–646; `change_manager.py` lines 107–159.

---

## File Deletion on Feature Removal

**Verdict: NOT IMPLEMENTED**

No code in the change pipeline deletes files from disk when a feature is removed. Searched across the full `backend/app/` tree for: `shutil.rmtree`, `unlink`, `os.remove`, `FileRegistry.mark_deleted`, `delete.*file`. No hits related to feature removal.

`analyze_file_impact()` produces a `files_to_regenerate` list (files whose content needs rewriting), but:
- This list is stored in `project.json` as `file_impact_analysis`.
- No agent reads this list to perform deletions.
- Files in `files_to_regenerate` are only updated if the pipeline re-runs the backend/frontend stages, which write new content to those paths. Files that were created in prior sprints but are no longer needed simply remain on disk unchanged.

The `FileRegistry` (referenced in `write_sprint_delta.py` and `file_planner.py`) tracks which files have been created across sprints for prompt context, but has no `mark_deleted()` API.

---

## Change Pipeline Assessment

| Capability | Status | Evidence |
|---|---|---|
| API endpoint for change submission | IMPLEMENTED | `POST /workflow/{id}/change` in `api/workflow.py:686` |
| Change type classification via LLM | IMPLEMENTED | `ImpactAnalyzer._classify_change()` in `impact_analyzer.py:247` |
| Stage-level impact computation | IMPLEMENTED | `ImpactAnalyzer.analyze()` with `STAGE_DEPENDENCIES` DAG |
| File-level impact computation | CONDITIONAL | `analyze_file_impact()` — only works when all 3 intelligence-layer components are wired |
| Persistent change record | IMPLEMENTED | `requirement_changes[]` in `project.json` after `apply()` |
| User confirmation gate | IMPLEMENTED | Two-step submit → confirm flow |
| Sprint-level impact (which sprint numbers) | NOT IMPLEMENTED | Always hardcoded `sprints_to_replan=[1]` |
| Sprint task creation for added features | NOT IMPLEMENTED | Relies on full stage re-run |
| Pipeline resume after confirmation | NOT IMPLEMENTED | `RESUMING_FROM_CHANGE` state not handled by `PipelineSupervisor._run_impl()` |
| Auto-resume after confirmation | NOT IMPLEMENTED | No auto-resume; user must call `/continue` |
| File deletion on feature removal | NOT IMPLEMENTED | No deletion code anywhere in change path |
| Artifact cleanup for prior sprints | NOT IMPLEMENTED | Old sprint artifacts remain |
| Active sprint interrupt | NOT IMPLEMENTED | No interrupt; sprint runs to completion |
| Change queue during active sprint | NOT IMPLEMENTED | No queue; change sits as pending_change |
| BugAnalyst spec/arch rollback | PARTIAL | Calls ChangeManager but does not auto-resume |
| Infinite rollback prevention | IMPLEMENTED | `_MAX_ARCH_ROLLBACK_ITERATIONS = 2` |
| CHANGE_REQUESTED state | IMPLEMENTED | Set by `submit()` |
| IMPACT_ANALYZED state | NOT USED | Defined in `project_state.py` but never set by any code |
| REPLANNING state | NOT USED | Defined in `project_state.py` but never set by any code |
| RESUMING_FROM_CHANGE state | PARTIALLY IMPLEMENTED | Set by `apply()`, but not handled by pipeline supervisor |

---

## Verdict

### What actually works for change management today

1. The three-endpoint API flow (submit → confirm → cancel) is implemented end-to-end.
2. Impact analysis correctly classifies change type via LLM and computes which pipeline stages must re-run using a static DAG.
3. Change records are persisted to `project.json` with a full audit trail (`requirement_changes[]`).
4. The user confirmation gate works — no change is applied without explicit `confirmed=True`.
5. BugAnalyst rollback for `spec_bug`/`architecture_bug` correctly triggers the ChangeManager with a 2-iteration guard against infinite loops.
6. File-level impact analysis works if (and only if) the intelligence layer components are wired in the DI container.

### What is missing

1. **Critical — Pipeline resume after change:** `RESUMING_FROM_CHANGE` is not in any of `DISCOVERY_STATES`, `SPRINT_STATES`, or `RELEASE_STATES` in `pipeline_supervisor.py`. After `apply()` sets the state, calling `/workflow/{id}/continue` causes the pipeline supervisor to fall through to the terminal-states handler and return `success=False` without executing anything. Changes are effectively dead-ended after confirmation. **This makes the entire change-management loop non-functional at the pipeline level.**

2. **Sprint-number-aware replanning is absent:** `sprints_to_replan` is hardcoded to `[1]` for any code-touching change. Multi-sprint projects that change Sprint 2 or 3 receive incorrect sprint impact data.

3. **No file deletion:** Removing a feature leaves all previously generated files on disk. The workspace accumulates orphaned code after remove_feature changes.

4. **No active sprint interrupt:** A change submitted during a running sprint is silently queued in `project.json` and does not affect the in-flight executor.

5. **Three states (`IMPACT_ANALYZED`, `REPLANNING`) are defined in `ProjectState` but never used.** Their presence in the enum suggests incomplete implementation of a more granular replanning flow.

6. **No auto-resume:** Even if the RESUMING_FROM_CHANGE gap were fixed, the pipeline requires a manual `/continue` call after change confirmation. The design-approval endpoint auto-resumes but change confirmation does not.

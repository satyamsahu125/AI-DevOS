# Audit 2: Agile Architecture Audit

> Auditor: Principal Agile Architecture Auditor  
> Date: 2026-08-10  
> Scope: Source code only — documentation and docstrings not trusted.  
> Files examined: sprint.py, project_state.py, pipeline_supervisor.py, sprint_executor.py, sprint_planner.py, sprint_review.py, scrum_master.py, workflow/manager.py, workflow/change_manager.py, workflow/impact_analyzer.py, api/workflow.py, api/gates.py

---

## Product Backlog

**Finding:** No persistent product backlog data structure exists. The `StrategicBriefSchema` has a `deferred_to_backlog: list[str]` field, but it is a plain text list inside a one-shot LLM artifact. There is no living backlog object that survives between sprints, no prioritization mechanism, no carry-over logic, and no blocked-story flag.

**Evidence:**
- `F:\AI-DevOS3\backend\app\shared\schemas\strategic_brief_schema.py:22` — `deferred_to_backlog: list[str] = Field(default_factory=list)` — declared field only.
- `F:\AI-DevOS3\backend\app\actions\write_strategic_brief.py:18` — LLM prompt mentions "deferred_to_backlog" as an output field; nothing reads it back at sprint planning time.
- `F:\AI-DevOS3\backend\app\shared\models\sprint.py:29` — `Sprint.features: list[str]` — user stories are embedded strings inside a sprint, not references to a backlog.
- No file anywhere contains a `Backlog` class or a backlog API endpoint.

**Verdict: NOT IMPLEMENTED**

---

## Sprint Backlog

**Finding:** A sprint-specific task list exists on `Sprint.tasks: list[SprintTask]` (sprint.py), and `SprintTask` has `depends_on: list[str]` and `status: str` fields. However, `SprintExecutor.run()` never reads `sprint.tasks`, `SprintTask.depends_on`, or `SprintTask.status`. The executor runs a hardcoded sequence of stages (ScrumMaster → SprintDeltaPlanner → FileStructurePlanner → BackendDeveloper → FrontendDeveloper → SprintDeploy → SprintReview) regardless of what tasks the sprint model declares.

**Evidence:**
- `F:\AI-DevOS3\backend\app\shared\models\sprint.py:15-22` — `SprintTask` model with `depends_on` and `status` fields.
- `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py:82-155` — `SprintExecutor.run()` receives a `Sprint` object but only reads `sprint.sprint_number`, `sprint.name`, `sprint.goal`, and `sprint.features`. Never reads `sprint.tasks`.
- `sprint_executor.py:93-147` — Stage execution order is hardcoded: `_run_scrum_master → _run_sprint_delta → _run_file_planner → _run_engine_stage("BackendDeveloper") → _run_engine_stage("FrontendDeveloper") → _run_sprint_deploy_and_review`.
- No code path consults `SprintTask.depends_on` for ordering or `SprintTask.status` for tracking.
- The sprint backlog cannot change mid-sprint (no API endpoint writes to `sprint.tasks`).

**Verdict: NOT IMPLEMENTED** — Sprint tasks are planning metadata only; dependency and status fields are dead weight.

---

## Sprint Completion Criteria

**Finding:** A sprint is marked "complete" when: (a) `BackendDeveloper` stage returns success, AND (b) `FrontendDeveloper` stage returns success, AND (c) sandbox verification passes (install → build → test). Human approval is not a gate. The `SprintReview` agent runs but its `accepted` field is not checked before calling `mark_sprint_complete()`.

**Evidence:**
- `F:\AI-DevOS3\backend\app\workflow\sprint_executor.py:125-147`:
  ```python
  all_success = backend_result.success and frontend_result.success
  if all_success:
      sandbox_success, sandbox_message = self._run_sandbox_verification(project_id, sprint)
      if not sandbox_success:
          return SprintResult(sprint_complete=False, success=False, ...)
      self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
      self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
  ```
- `sprint_executor.py:361-391` — `_run_sprint_deploy_and_review()` calls `SprintReview` through the engine, but its result is only logged — never used to gate `mark_sprint_complete()`.
- Completion criteria: (a) agents returned success = YES, (b) files written = YES (implied by agent success), (c) build passed = YES (sandbox gate), (d) tests passed = PARTIAL (sandbox checks, but test failures don't block sprint per `SprintResult` logic — only `build.success` is checked at line 297), (e) user approved = NO.

**Verdict: PARTIAL** — Code correctness gate exists (build must pass), but no human acceptance gate.

---

## Sprint Review (Human Gate)

**Finding:** `SprintReviewAgent` is fully automated — it receives `user_stories`, `deploy_status`, and `qa_findings` (all LLM-generated) and produces an LLM review of the LLM's own output. There is no mechanism for a human to reject a sprint. The `accepted: bool` field in the review output is set by the LLM and never checked by `SprintExecutor` or `PipelineSupervisor` before advancing.

**Evidence:**
- `F:\AI-DevOS3\backend\app\agents\sprint_review.py:40-72` — System prompt: "You are a Product Manager leading a sprint review meeting." The LLM plays all roles — Product Manager, deployed status checker, and QA validator.
- `sprint_review.py:154-228` — `review_sprint()` accepts LLM-generated `user_stories`, `deploy_status`, `qa_findings`; outputs an `accepted` bool decided by the LLM.
- `sprint_executor.py:379` — `review_result = self._engine.run(project_id, "SprintReview", "")` — result is returned but never read. The code only calls the engine; there is no `if review_result.structured["accepted"] == False: return SprintResult(success=False)` guard.
- No API endpoint exists for a human to POST "sprint N is rejected."
- No `SPRINT_COMPLETE` state transition is ever assigned; after all sprints pass, the system jumps directly to `ALL_SPRINTS_COMPLETE`.

**Verdict: NOT IMPLEMENTED** — Sprint review is a simulated LLM ceremony. No human gate exists and the review result has no programmatic effect on pipeline progression.

---

## User Feedback Loop

**Finding:** There is no post-sprint user feedback loop. The system pauses for human input at three points only: pre-development Q&A (clarification questions), architecture review, and design review. After each sprint completes, the pipeline immediately starts the next sprint with no pause.

**Evidence:**
- `F:\AI-DevOS3\backend\app\api\workflow.py` — API endpoints examined: `/workflow/start`, `/workflow/{id}/continue`, `/workflow/{id}/design-review`, `/workflow/{id}/qa`, `/workflow/{id}/change`, `/workflow/{id}/approve`. No endpoint named `sprint-feedback`, `sprint-review`, or similar.
- `pipeline_supervisor.py:440-517` — `_run_sprints()` loops over sprints. Between sprints: no state pause, no `requires_user_action=True`, no wait for human signal.
- `pipeline_supervisor.py:406-417` — `SPRINT_PLAN_REVIEW_PENDING` is handled as a gate, but that state is never actually set during normal pipeline execution (see ProjectState table below).
- No `AWAITING_SPRINT_REVIEW` state exists. The closest state, `AWAITING_HUMAN_APPROVAL`, is never assigned (only checked in a dead code branch at `api/workflow.py:598`).

**Verdict: NOT IMPLEMENTED**

---

## Requirement Change Handling

**Finding:** A real requirement change mechanism exists. A user can POST to `/workflow/{project_id}/change` at any time (even mid-sprint) with a text description. The `ImpactAnalyzer` classifies the change type (add_feature, modify_ui, modify_api, etc.), identifies which stages must re-run using dependency rules, computes safe stages to preserve, and stores a `pending_change` in `project.json`. The user confirms via `/change/confirm`, which removes affected stages from `stages_completed` and transitions to `RESUMING_FROM_CHANGE`.

**Evidence:**
- `F:\AI-DevOS3\backend\app\api\workflow.py:686-755` — Three endpoints: `POST /change`, `POST /change/confirm`, `POST /change/cancel`.
- `F:\AI-DevOS3\backend\app\workflow\change_manager.py:48-159` — `submit()` calls `ImpactAnalyzer.analyze()`, transitions to `CHANGE_REQUESTED`. `apply()` removes affected stages from `stages_completed`, transitions to `RESUMING_FROM_CHANGE`.
- `F:\AI-DevOS3\backend\app\workflow\impact_analyzer.py:33-74` — `CHANGE_TYPE_IMPACT` dict maps 7 change types to affected stage lists. `_add_downstream()` cascades to dependent stages.
- `impact_analyzer.py:144` — `sprints_to_replan=[1] if needs_replan else []` — hardcoded sprint 1 as replan target; does not identify which sprint is actually affected.

**Verdict: IMPLEMENTED** (with caveats — sprint-granularity replanning is rudimentary, always targeting sprint 1)

---

## Replanning Mechanism

**Finding:** Replanning operates at **stage granularity**, not sprint granularity. When `apply()` is called, the pipeline removes affected stages from `stages_completed` and re-runs from the first affected stage. This is a genuine replan mechanism. However, it does not identify which sprint tasks are invalidated — it invalidates whole stages (e.g., "backend", "frontend"). Sprint 2 running when Sprint 1's architecture changes: the system would remove "architect" and all downstream stages from `stages_completed`, causing the entire pipeline to re-run from architecture — not a targeted sprint-level replan.

**Evidence:**
- `change_manager.py:142-148` — `self._workspace.update_project_json(project_id, {"stages_completed": safe_stages, ...})` then `RESUMING_FROM_CHANGE`.
- `impact_analyzer.py:135-145` — `sprints_to_replan=[1] if needs_replan else []` — always targets sprint 1 regardless of which sprint is in progress.
- No code checks `current_sprint_number` when computing `sprints_to_replan`.
- `analyze_file_impact()` (impact_analyzer.py:178-245) does file-level analysis, but only when all three of `_file_indexer`, `_dep_graph`, and `_code_summarizer` are wired — and `ImpactAnalyzer.__init__` defaults all three to `None` (line 94-98). In the standard container wiring at `manager.py:112-118`, only `llm_manager` and `artifact_manager` are passed; the intelligence layer args are not.

**Verdict: PARTIAL** — Stage-level replanning works. Sprint-level targeting and file-level intelligence are either placeholder (hardcoded sprint 1) or gated behind optional wiring that is not connected in default configuration.

---

## ProjectState — Declared vs Actually Used

| State | Declared | Ever Assigned by update_state | By What Code |
|-------|----------|-------------------------------|-------------|
| EMPTY | ✓ | ✓ | workspace/manager.py:101 (init) |
| CLARIFYING | ✓ | ✓ | workflow/manager.py:243; project/initializer.py:44 |
| QA_PENDING | ✓ | ✓ | qa_orchestrator.py:166 |
| QA_IN_PROGRESS | ✓ | ✓ | qa_orchestrator.py:95; api/workflow.py:543; api/project.py:204 |
| QA_COMPLETE | ✓ | NOT ASSIGNED | Referenced in RELEASE_STATES routing set only |
| REQUIREMENTS_READY | ✓ | ✓ | qa_orchestrator.py:118, 244, 285 |
| ARCHITECTURE_READY | ✓ | ✓ | api/gates.py:125, 147 |
| ARCHITECTURE_REVIEW_PENDING | ✓ | ✓ | pipeline_supervisor.py:339 |
| DESIGN_READY | ✓ | ✓ | api/workflow.py:200 |
| DESIGN_REVIEW_PENDING | ✓ | ✓ | pipeline_supervisor.py:357 |
| DESIGN_APPROVED | ✓ | ✓ | pipeline_supervisor.py:372; api/workflow.py:181; api/gates.py:172, 193 |
| SPRINT_PLAN_REVIEW_PENDING | ✓ | NOT ASSIGNED | Checked in manager.py:256 and pipeline_supervisor.py:404, but never set by update_state |
| SPRINT_PLAN_READY | ✓ | ✓ | api/gates.py:217, 243 |
| SPRINT_IN_PROGRESS | ✓ | ✓ | pipeline_supervisor.py:406; change_manager.py:122 |
| SPRINT_COMPLETE | ✓ | NOT ASSIGNED | Never set; pipeline goes SPRINT_IN_PROGRESS → ALL_SPRINTS_COMPLETE |
| SPRINT_BLOCKED | ✓ | NOT ASSIGNED | In SPRINT_STATES routing set (pipeline_supervisor.py:72) but update_state never called with it |
| ALL_SPRINTS_COMPLETE | ✓ | ✓ | pipeline_supervisor.py:422, 509 |
| AWAITING_HUMAN_APPROVAL | ✓ | NOT ASSIGNED | Only checked in dead-code branch at api/workflow.py:598 |
| CHANGE_REQUESTED | ✓ | ✓ | change_manager.py:95 |
| IMPACT_ANALYZED | ✓ | NOT ASSIGNED | Never appears in any update_state or transition call |
| REPLANNING | ✓ | NOT ASSIGNED | Never appears in any update_state or transition call |
| RESUMING_FROM_CHANGE | ✓ | ✓ | change_manager.py:148; pipeline_supervisor.py:639 |
| DEPLOYABLE | ✓ | ✓ | pipeline_supervisor.py:733 |
| DONE | ✓ | NOT ASSIGNED | Only checked in status display (api/workflow.py:345) |
| FAILED | ✓ | ✓ | qa_orchestrator.py:320; pipeline_supervisor.py crash handler |
| PAUSED | ✓ | NOT ASSIGNED | Never appears in any update_state or transition call |

**Summary:** Of 25 declared states, 14 are actually assigned by runtime code. 11 are either declaration-only (IMPACT_ANALYZED, REPLANNING, PAUSED, DONE, SPRINT_COMPLETE, SPRINT_BLOCKED, QA_COMPLETE) or routing-only references that are checked but never set (SPRINT_PLAN_REVIEW_PENDING, AWAITING_HUMAN_APPROVAL).

---

## Agile Maturity Assessment

| Dimension | Score | Evidence |
|-----------|-------|----------|
| Product Backlog (persistent, prioritized) | 1/10 | `deferred_to_backlog` is a string field in a one-shot artifact; no living backlog exists |
| Sprint Backlog (separate, executable task list) | 1/10 | `SprintTask` model exists but `sprint.tasks` is never read by `SprintExecutor` |
| Sprint Goal Clarity | 6/10 | `Sprint.goal` and `Sprint.features` are populated and injected into agent context |
| Sprint Completion Gate (human acceptance) | 1/10 | Completion = agent success + build passes; no human approval step |
| Sprint Review (real human feedback) | 1/10 | Fully automated LLM simulation; review result has no programmatic effect |
| Sprint Retrospective | 4/10 | `RetroAgent` runs as part of the release phase but it's automated, not human-led |
| User Feedback Loop (between sprints) | 1/10 | No inter-sprint pause; no feedback API endpoint; pipeline runs sprints sequentially |
| Requirement Change Handling | 7/10 | Full impact analysis + stage invalidation + rerun mechanism is real and wired |
| Replanning | 4/10 | Stage-level replanning works; sprint-level targeting is hardcoded to sprint 1 |
| Adaptive Prioritization | 1/10 | No backlog reordering; no story carry-over; sprint plan is fixed after generation |

---

## Direct Verdict

**[PARTIALLY AGILE — Sequential Pipeline with Agile Scaffolding]**

**Explanation:**

The system is best described as a **fixed sequential pipeline that wears Agile terminology**. The core execution path is deterministic and sequential: Discovery → Sprints (1..N, no pause between them) → Release → DEPLOYABLE. Sprint tasks (`SprintTask.depends_on`, `SprintTask.status`) are declared in the model but never consulted by the executor. The sprint review is a fully automated LLM ceremony with no human gate and whose `accepted` verdict has zero programmatic effect on pipeline progression.

Where the system achieves genuine Agile behavior is at the **edges of the pipeline**: the pre-development Q&A loop is a real clarification mechanism; the architecture and design gates are real human pauses with feedback-driven revision; and the requirement change mechanism (POST `/change` → impact analysis → stage invalidation → rerun) is a substantive adaptive replanning capability.

The gap is that **no Agile event occurs between the start of Sprint 1 and the end of Sprint N**. A user cannot reject a sprint, reprioritize the backlog, carry a story over, or trigger a targeted mid-sprint replan. The states `SPRINT_BLOCKED`, `REPLANNING`, `IMPACT_ANALYZED`, and `PAUSED` are all declared but never assigned by any code path. The system therefore satisfies Agile at the project-setup phase and the requirement-change path, but the sprint execution itself is a batch pipeline.

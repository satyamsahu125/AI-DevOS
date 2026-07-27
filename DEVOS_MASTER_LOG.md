# AI DevOS — Master Architecture & Execution Log

> **Purpose:** Single source of truth for what was broken, what was fixed, what needs to change, and what comes next.
> Every agent and every session MUST read this file before executing any change.
> Every fix or failed attempt MUST append a log entry at the bottom.

---

## HOW TO USE THIS FILE

1. **Before any work:** Read sections 1–4 to understand current state.
2. **Before any code change:** Check Section 4 (Implementation Tracker) for the current active task.
3. **After any work (pass or fail):** Append a timestamped entry to Section 5 (Execution Log).
4. **When updating architecture:** Update Section 2 and Section 3 in place.
5. **Never delete history** — only append and mark items done.

---

## SECTION 1 — WHAT WE GOT WRONG (Past Bugs, All Fixed)

These bugs were found in live runs and are now fixed. Understand them before touching related code.

### BUG-001 — SprintPlan.created_at crash
- **Symptom:** `pydantic_core.ValidationError: created_at input is too short` killed `_run_next_sprint()`
- **Root cause:** LLM left `created_at = ""`. `SprintPlan` expects `datetime`, not empty string.
- **Fix:** `workspace/manager.py` → `get_sprint_plan()` defaults empty string to `datetime.now(utc)` before validation.
- **Commit:** `d07934f`
- **Status:** ✅ FIXED

### BUG-002 — stages_completed wiped on every /continue
- **Symptom:** Pipeline restarted from scratch on every Continue click.
- **Root cause:** `_sanitize_stages_completed` deleted everything because StrategicReview was never written.
- **Fix:** Added `_STATE_IMPLIED_STAGES` dict — sanitizer merges implied stages from current ProjectState so old projects survive.
- **Commit:** `9766370`
- **Status:** ✅ FIXED

### BUG-003 — DomainResearcher returning wrong domain
- **Symptom:** Hotel booking project classified as "food delivery" domain.
- **Root cause:** System prompt contained only food delivery examples; LLM copied them.
- **Fix:** `prompt/domain_research_builder.py` — rewrote prompt with multi-domain examples + `CRITICAL RULE: derive domain from actual request`.
- **Commit:** `d07934f`
- **Status:** ✅ FIXED

### BUG-004 — /approve-design required manual /continue
- **Symptom:** User approved design, nothing happened, had to click Continue manually.
- **Root cause:** `post_design_review()` endpoint didn't fire a background task after approval.
- **Fix:** `api/workflow.py` — added `BackgroundTasks` param; fires `manager.run()` as background task on both approve and revision.
- **Commit:** `d07934f`
- **Status:** ✅ FIXED

### BUG-005 — Frontend blank panel for clarifying/paused state
- **Symptom:** White/blank ChatPanel shown when state was `clarifying` and status was `paused`.
- **Root cause:** No branch in WorkspacePage for this state combination.
- **Fix:** `frontend/src/pages/WorkspacePage.tsx` — added `showStarting` flag, dedicated "Pipeline initialising" panel with inline Continue button.
- **Commit:** `4ccf2db`
- **Status:** ✅ FIXED

### BUG-006 — project.json corruption (JSONDecodeError: Extra data)
- **Symptom:** `JSONDecodeError: Extra data: line 29 column 4` on concurrent writes.
- **Root cause:** Two threads both read project.json, both wrote back → partial overwrite produced two JSON objects concatenated.
- **Fix:** `workspace/manager.py` — per-project `threading.Lock` + atomic write via `tempfile.mkstemp` + `os.replace`. Added corruption-tolerant reader with `raw_decode` fallback.
- **Commit:** `9766370`
- **Status:** ✅ FIXED

### BUG-007 — max_tokens kwarg crash in QA/DevOps/Document agents
- **Symptom:** `TypeError: LLMManager.generate_text() got an unexpected keyword argument 'max_tokens'`
- **Root cause:** Three action classes passed `max_tokens` kwarg that wasn't in `generate_text()` signature.
- **Fix:** `llm/manager.py` — added `max_tokens: int | None = None` parameter; overrides config when set.
- **Commit:** `4e1de10`
- **Status:** ✅ FIXED

### BUG-008 — Silent stage failures in ALL_SPRINTS_COMPLETE
- **Symptom:** QA/DevOps/Document failed silently. Retro still ran and showed success.
- **Root cause:** `ALL_SPRINTS_COMPLETE` handler ignored stage results (no result check).
- **Fix:** `workflow/manager.py` — loop with `logger.WARNING` on failure but continues (non-fatal). Future: TechLead/BugAnalyst will handle failure routing properly.
- **Commit:** `4e1de10`
- **Status:** ✅ FIXED (partially — proper failure routing is part of new architecture)

### BUG-009 — StrategicReview never written to stages_completed
- **Symptom:** Q&A path processed StrategicReview inline, never added it to `stages_completed`. Sanitizer then deleted all subsequent stages.
- **Root cause:** `QA_IN_PROGRESS` handler ran StrategicReview outside the engine, so engine never recorded it.
- **Fix:** `workflow/manager.py` — `QA_IN_PROGRESS` handler manually inserts `Stage.StrategicReview.value` into `stages_completed` after Q&A processing.
- **Commit:** `9766370`
- **Status:** ✅ FIXED

---

## SECTION 2 — CURRENT ARCHITECTURE PROBLEMS (What's Wrong Now)

These are NOT bugs — they are architectural limitations that cause the pipeline to behave wrong at scale.

### ARCH-001 — QA runs once at end, not per sprint
- **Problem:** QA tests all sprints together at the end. A Sprint 1 bug is caught after Sprint 3 is built. This is wrong.
- **Real behaviour:** QA should test each sprint immediately after coding completes. Sprint 2 should never start if Sprint 1 fails QA.
- **Required change:** `QAAgent` moves into the sprint execution loop. Runs after every sprint.

### ARCH-002 — No feedback loop — bugs have nowhere to route
- **Problem:** When QA finds a bug, there is no agent to analyse root cause. The pipeline either fails or silently continues. No distinction between "wrong code" and "wrong spec".
- **Real behaviour:** A QA engineer files a ticket. It gets triaged. Code bugs go to dev. Spec bugs go to PM. Architecture bugs go to the architect.
- **Required change:** New `BugAnalystAgent`. Reads QA findings + code + specs, classifies: `code_bug | spec_bug | architecture_bug | security_violation`. Supervisor routes fix to the right agent.

### ARCH-003 — No code review within a sprint
- **Problem:** Backend/Frontend agents write code. Nothing checks it before QA. Architecture violations, style issues, and obvious errors reach production.
- **Real behaviour:** A Tech Lead reviews all PRs before merge.
- **Required change:** New `TechLeadAgent`. Runs after dev, before QA, within each sprint.

### ARCH-004 — Sequential state machine is hardcoded, not graph-driven
- **Problem:** `WorkflowManager` has a long `if/elif` chain over `ProjectState`. Adding a feedback loop (QA → BugAnalyst → dev) requires inserting more state transitions. The state machine grows unboundedly and becomes unmaintainable.
- **Real behaviour:** A dependency graph. Each agent knows its inputs. Supervisor resolves who can run next based on what's complete.
- **Required change:** `PipelineSupervisor` (3-phase graph) + `SprintSupervisor` (per-sprint graph with conditional feedback edges). State machine becomes thin adapter.

### ARCH-005 — Flat artifact storage, no sprint scoping
- **Problem:** All artifacts go to `artifacts/{Stage}.md`. Sprint 2's QA report overwrites Sprint 1's. No audit trail. Agents get wrong-sprint context.
- **Required change:** Versioned, sprint-scoped artifact store:
  ```
  artifacts/project/user_stories.json       ← project-level, versioned
  artifacts/sprint_1/qa_findings.json       ← sprint-scoped
  artifacts/sprint_1/bug_analysis.json
  artifacts/sprint_2/...
  artifacts/release/...
  ```

### ARCH-006 — No staging deploy per sprint
- **Problem:** Code is deployed once at the end. No validation that each sprint's increment actually runs.
- **Required change:** Lightweight `SprintDeployAgent` runs after QA passes each sprint. Deploys to staging. SprintReviewAgent validates demo.

### ARCH-007 — Memory used for sprint-scoped data it's not suited for
- **Problem:** Per-sprint task lists, QA findings, and build results are stored in memory (LLM-readable, unstructured). Memory should only hold project-level knowledge.
- **Required change:** Sprint artifacts → JSON files in `artifacts/sprint_N/`. Memory → only architecture rationale, design principles, sprint retro summaries.

---

## SECTION 3 — NEW ARCHITECTURE (Target State)

### 3.1 — Agent Roster

**Discovery layer (run once per project):**
| Agent | File | Status |
|---|---|---|
| DomainResearcherAgent | `agents/domain_researcher.py` | ✅ exists — keep |
| ClarificationAgent (Business Analyst) | `agents/clarification.py` | ✅ exists — rename + strengthen |
| ProductOwnerAgent (Product Manager) | `agents/product_owner.py` | ✅ exists — add UPDATE mode for spec fixes |
| ArchitectAgent | `agents/architect.py` | ✅ exists — add UPDATE mode for arch fixes |
| DesignerAgent | `agents/designer.py` | ✅ exists — keep |
| SecurityAgent | `agents/security.py` | ✅ exists — keep |
| SprintPlannerAgent | `agents/sprint_planner.py` | ✅ exists — keep |

**Sprint execution layer (repeat every sprint):**
| Agent | File | Status |
|---|---|---|
| ScrumMasterAgent | `agents/scrum_master.py` | ✅ exists — keep |
| FilePlannerAgent | `agents/file_planner.py` | ✅ exists — keep |
| BackendDeveloperAgent | `agents/backend.py` | ✅ exists — keep |
| FrontendDeveloperAgent | `agents/frontend.py` | ✅ exists — keep |
| TechLeadAgent | `agents/tech_lead.py` | ❌ CREATE |
| QAAgent (per-sprint) | `agents/qa.py` | ⚠️ MOVE inside sprint loop |
| BugAnalystAgent | `agents/bug_analyst.py` | ❌ CREATE |
| SprintDeployAgent | `agents/sprint_deploy.py` | ❌ CREATE |
| SprintReviewAgent | `agents/sprint_review.py` | ❌ CREATE |
| SprintRetroAgent | `agents/retro.py` | ⚠️ SPLIT from RetroAgent |

**Release layer (run once after all sprints):**
| Agent | File | Status |
|---|---|---|
| RegressionQAAgent | `agents/qa.py` | ⚠️ REUSE QAAgent with full-regression context |
| ProductionDeployAgent | `agents/devops.py` | ⚠️ RENAME from DevOpsAgent |
| TechnicalWriterAgent | `agents/document.py` | ✅ exists — keep |
| ProjectRetroAgent | `agents/retro.py` | ⚠️ SPLIT from RetroAgent |

### 3.2 — Sprint Execution Flow with Feedback Loop

```
ScrumMaster → tasks.json
    ↓
FilePlanner → file_plan.json
    ↓
Backend + Frontend (parallel)
    ↓
TechLead → tech_review.json
    ├─ violations → back to dev (max 3 iterations)
    └─ approved ↓
QAEngineer → qa_findings.json
    ├─ all pass → SprintDeploy
    └─ failures ↓
        BugAnalyst → bug_analysis.json
            ├─ code_bug       → re-run Backend/Frontend
            ├─ spec_bug       → ProductOwner updates user_stories → re-run dev
            ├─ architecture_bug → Architect updates design → re-run dev
            └─ blocked        → SPRINT_BLOCKED (human escalation)
    ↓
SprintDeploy → deploy_status.json (staging)
    ↓
SprintReviewer → sprint_review.json
    ↓
SprintRetro → retro.json → writes summary to memory
```

**Retry limits (configurable in settings.yml):**
- dev → TechLead loop: **max 3 iterations**
- dev → QA → BugAnalyst loop: **max 3 iterations**
- spec/arch update → dev → QA: **max 2 iterations**
- Beyond limit → state: `SPRINT_BLOCKED` → requires human action

### 3.3 — Artifact Store Structure

```
temp-workspace/{project_id}/
  artifacts/
    project/
      domain.json              ← DomainResearcher output
      requirements.json        ← ClarificationAgent output
      user_stories.json        ← ProductOwner output (versioned: v1, v2...)
      architecture.json        ← Architect output (versioned)
      design.json              ← Designer output
      security_rules.json      ← Security output
      sprint_plan.json         ← SprintPlanner output
    sprint_1/
      tasks.json               ← ScrumMaster
      file_plan.json           ← FilePlanner
      tech_review.json         ← TechLead (each iteration)
      qa_findings.json         ← QA (each run)
      bug_analysis.json        ← BugAnalyst (when QA fails)
      deploy_status.json       ← SprintDeploy
      sprint_review.json       ← SprintReviewer
      sprint_retro.json        ← SprintRetro
    sprint_2/ ...
    release/
      regression_qa.json
      deploy_manifest.json
      documentation.json
      project_retro.json
  memory/                      ← LLM-readable, project-level only
    architecture_decisions.md
    design_principles.md
    sprint_summaries.md
```

### 3.4 — Orchestration: Two Supervisors

**PipelineSupervisor** (`workflow/pipeline_supervisor.py`):
- Manages 3 phases: Discovery → Sprints → Release
- Holds Pipeline Dependency Graph
- Calls SprintSupervisor for each sprint

**SprintSupervisor** (`workflow/sprint_supervisor.py`):
- Manages one sprint's internal execution loop
- Holds Sprint Dependency Graph with conditional feedback edges
- Manages retry counters, escalation to `SPRINT_BLOCKED`

**ArtifactStore** (`workspace/artifact_store.py`):
- Versioned artifact read/write
- Scoped by `project`, `sprint_N`, or `release`
- Returns latest version by default; full version history available

### 3.5 — Memory Boundary (Strict)

| Data | Storage | Why |
|---|---|---|
| Architecture rationale | Memory | LLMs need to read it, changes rarely |
| Design principles | Memory | Same |
| Sprint retro summaries | Memory | Cross-sprint context for next sprint |
| User stories + acceptance criteria | Artifact JSON | Structured, versioned, machine-readable |
| Architecture doc (system design) | Artifact JSON | Versioned on update |
| Per-sprint task list | Artifact JSON | Sprint-scoped, not needed after sprint |
| QA findings | Artifact JSON | Sprint-scoped |
| Bug analysis | Artifact JSON | Sprint-scoped |
| Code files | Workspace files | Never in memory/artifacts |

---

## SECTION 4 — IMPLEMENTATION TRACKER

### Phase 1 — Foundation: ArtifactStore + Sprint Folders
> No behavior change — just restructures where artifacts live.

| Task | Status | Notes |
|---|---|
|---|
| Create `workspace/artifact_store.py` | ✅ DONE | Versioned read/write, sprint-scoped, stdlib only |
| Add sprint folder creation on sprint start | ✅ DONE | `WorkspaceManager.create_sprint_folder()` -- idempotent |
| Migrate existing artifact reads/writes to ArtifactStore | ✅ DONE | `_persist_to_artifact_store()` in WorkflowManager; non-fatal mirror; `.md` preserved |
| Update `WorkspaceLayout` to include sprint dirs | ✅ DONE | `artifacts/project/` + `artifacts/release/` static; sprint_N dynamic |

### Phase 2 — Sprint Feedback Loop
> Core new behavior: QA runs per sprint, bug routing, retry gates.

| Task | Status | Notes |
|---|---|---|
| Create `agents/bug_analyst.py` | ✅ DONE | Root cause classifier -- 4 types, ArtifactStore write in analyse() |
| Create `agents/tech_lead.py` | ✅ DONE | Code review per sprint -- approved/violations JSON, ArtifactStore write in review() |
| Create `agents/sprint_deploy.py` | ⏳ PENDING | Lightweight staging deploy |
| Create `agents/sprint_review.py` | ⏳ PENDING | Demo vs acceptance criteria |
| Evolve `agents/qa.py` -- per-sprint mode | ⏳ PENDING | Structured JSON output, reads sprint artifacts |
| Create `workflow/sprint_supervisor.py` | ⏳ PENDING | Sprint graph + feedback edges + retry gates |
| Add `SPRINT_BLOCKED` to ProjectState | ⏳ PENDING | New state for human escalation |
| Add retry configuration to settings.yml | ⏳ PENDING | `max_dev_iterations`, `max_qa_iterations` |

### Phase 3 — Replace State Machine with PipelineSupervisor
> Replaces the hardcoded if/elif chain in WorkflowManager.

| Task | Status | Notes |
|---|---|---|
| Create `workflow/pipeline_supervisor.py` | ⏳ PENDING | 3-phase graph traversal |
| Create `workflow/sprint_graph.py` | ⏳ PENDING | Sprint dep graph with conditional edges |
| Wire PipelineSupervisor into WorkflowManager | ⏳ PENDING | Manager becomes thin adapter |
| Retire sequential state machine | ⏳ PENDING | After supervisor is verified |

### Phase 4 — New Per-Sprint Agents
| Task | Status | Notes |
|---|---|---|
| Split `agents/retro.py` → SprintRetroAgent + ProjectRetroAgent | ⏳ PENDING | |
| Rename DevOpsAgent → ProductionDeployAgent | ⏳ PENDING | |
| Add UPDATE mode to ProductOwnerAgent | ⏳ PENDING | Takes bug_analysis, updates user_stories |
| Add UPDATE mode to ArchitectAgent | ⏳ PENDING | Takes bug_analysis, updates architecture |

### Phase 5 — Artifact Versioning
| Task | Status | Notes |
|---|---|---|
| Version user_stories.json on spec update | ⏳ PENDING | user_stories_v2.json + reason logged |
| Version architecture.json on arch update | ⏳ PENDING | Same |
| Audit log: why artifact was versioned | ⏳ PENDING | Written by BugAnalyst at time of update |

---

## SECTION 5 — EXECUTION LOG

> Every session appends here. Format: `[DATE] [PASS|FAIL|PARTIAL] — Description`
> Include: what was done, what files changed, what tests ran, what failed, what's next.

---

### [2026-07-20] PASS — Bug fixes batch 1 (BUG-001, BUG-003, BUG-004)
**Done:**
- Fixed SprintPlan.created_at crash (`workspace/manager.py`)
- Fixed DomainResearcher wrong domain (`prompt/domain_research_builder.py`)
- Fixed /approve-design no auto-resume (`api/workflow.py` + `tests/test_design_review.py`)

**Files changed:** `workspace/manager.py`, `prompt/domain_research_builder.py`, `api/workflow.py`, `tests/test_design_review.py`
**Tests:** All relevant tests pass
**Commit:** `d07934f`
**Next:** Fix BUG-002, BUG-005

---

### [2026-07-21] PASS — Bug fixes batch 2 (BUG-002, BUG-005, BUG-006, BUG-009)
**Done:**
- Fixed stages_completed wipe — added `_STATE_IMPLIED_STAGES` and state-aware sanitizer
- Fixed frontend blank panel for clarifying/paused state
- Fixed project.json corruption — per-project lock + atomic write + corruption-tolerant reader
- Fixed StrategicReview never written to stages_completed in Q&A path

**Files changed:** `workflow/manager.py`, `workspace/manager.py`, `frontend/src/pages/WorkspacePage.tsx`
**Tests:** All relevant tests pass
**Commit:** `9766370`, `4ccf2db`
**Next:** Fix BUG-007, BUG-008

---

### [2026-07-22] PASS — Bug fixes batch 3 (BUG-007, BUG-008)
**Done:**
- Fixed max_tokens kwarg crash in QA/DevOps/Document agents — added param to `LLMManager.generate_text()`
- Fixed silent stage failures in ALL_SPRINTS_COMPLETE — added loop with WARNING logging

**Files changed:** `llm/manager.py`, `workflow/manager.py`
**Tests:** All relevant tests pass
**Commit:** `4e1de10`
**Next:** Begin Phase 1 of new architecture — ArtifactStore + sprint folder structure

---

### [2026-07-27] — Architecture design session
**Done:**
- Full architecture designed: 3-layer agent model (Discovery / Sprint / Release)
- BugAnalyst feedback loop designed
- Artifact store structure designed (sprint-scoped, versioned)
- Two-supervisor model designed (PipelineSupervisor + SprintSupervisor)
- Memory boundary defined
- Implementation tracker created (Phases 1-5 above)
- This master log file created

**No code changed this session.**
**Next:** Phase 1 — Create `ArtifactStore` + sprint folder creation

---

### [2026-07-27] PASS — Phase 1: ArtifactStore + Sprint Folder Structure
**Done:**
- Created `backend/app/workspace/artifact_store.py` — `ArtifactStore` class:
  - `write(scope, name, data, version=False)` — versioned JSON persistence; `version=True` auto-increments to `_v2`, `_v3`, …
  - `read(scope, name)` — returns highest-versioned data automatically, `None` on miss
  - `exists(scope, name)` — checks any version on disk
  - `list_scope(scope)` — sorted base names, versions collapsed
  - Base path: `{workspace_root}/{project_id}/artifacts/{scope}/`
  - No external dependencies — stdlib only (json, pathlib, logging, re)
- Updated `backend/app/workspace/layout.py` — `WorkspaceLayout`:
  - Added `artifacts/project/` and `artifacts/release/` to `directories()` (created on workspace init)
  - Added `sprint_artifact_dir(sprint_number)` helper method
- Updated `backend/app/workspace/manager.py` — `WorkspaceManager`:
  - Added `create_sprint_folder(project_id, sprint_number) -> Path` (idempotent mkdir)
  - Wired call into `workflow/manager.py` `_run_sprint()` immediately after `set_current_sprint()` — ensures `artifacts/sprint_{N}/` exists before any agent runs
- Created `backend/tests/test_artifact_store.py` — 31 unit tests covering:
  - write, read, versioning (v2/v3 increment), base preserved after versioning
  - scope isolation (sprint_1 ≠ sprint_2 ≠ project ≠ release)
  - missing file returns None, list_scope collapses versions, returns sorted
  - create_sprint_folder: creates dir, returns path, idempotent, multiple sprints

**Files changed:**
- `backend/app/workspace/artifact_store.py` (NEW)
- `backend/app/workspace/layout.py` (updated)
- `backend/app/workspace/manager.py` (updated — create_sprint_folder + workflow wiring)
- `backend/tests/test_artifact_store.py` (NEW)

**Tests:** `31 passed in 0.37s` — all green ✅

**Commit:** `8a84e1b`

**No behavior changes** -- pure infrastructure refactor. No agents, no state machine logic, no API endpoints touched.

**Next:** Phase 2 -- Create `BugAnalystAgent` and `TechLeadAgent`

---

### [2026-07-27] PASS -- Phase 1 migration + Phase 2 agents (TechLead + BugAnalyst)

**Done:**

**Phase 1 remaining -- Migrate artifact reads/writes to ArtifactStore:**
- `WorkspaceManager.get_artifact_store(project_id)` -- deferred-import convenience factory added to `workspace/manager.py`
- `WorkflowManager._persist_to_artifact_store(project_id, stage, scope, artifact_name)` -- reads from ArtifactManager (existing flat `.md/.json`) and mirrors to sprint/project scoped ArtifactStore. Non-fatal (exception caught, logged at WARNING, pipeline continues). Existing `.md` write preserved for backward compat.
- Discovery layer wired (scope=`project`):
  - `ProductOwner` -> `user_stories`
  - `Architect` -> `architecture`
  - `Designer` -> `design`
  - `Security` -> `security_rules`
  - `SprintPlanner` -> `sprint_plan`
  - `ScrumMaster` -> `sprint_plan_tasks`
- Sprint layer wired (scope=`sprint_{N}`):
  - `FileStructurePlanner` -> `file_plan`
- Release layer wired (scope=`release`):
  - `QA` -> `qa_findings` (post-all-sprints QA)
- `datetime` import added to `workflow/manager.py`

**Phase 2 -- New agents:**
- `backend/app/agents/tech_lead.py` -- `TechLeadAgent`:
  - Reviews sprint code against architecture + security rules
  - Output: `{"approved": bool, "violations": [...], "summary": str, "iteration": N}`
  - `approved=False` safe-default when LLM returns empty/malformed JSON
  - `review(project_id, sprint_number, context_text, iteration)` convenience method (does ArtifactStore write)
  - `llm_backed=True` confirmed via `/agents` endpoint (no `execute()` override)
- `backend/app/agents/bug_analyst.py` -- `BugAnalystAgent`:
  - Classifies QA failures into: `code_bug | spec_bug | architecture_bug | security_violation`
  - Output: `{"type": ..., "root_artifact": ..., "affected_agent": ..., "fix_instruction": ..., "sprint": N, "iteration": N}`
  - Safe defaults applied when LLM returns empty JSON
  - `analyse(project_id, sprint_number, qa_findings, user_stories, architecture, file_plan, iteration)` convenience method
- `backend/app/shared/enums/stage.py` -- added `Stage.TechLead` and `Stage.BugAnalyst`
- `backend/app/agents/factory.py` -- registered `tech_lead` and `bug_analyst`
- `backend/tests/test_v1_pipeline_fixes.py` -- agent count snapshot updated 15->17 (correct: 2 new LLM-backed agents)

**Files changed:**
- `backend/app/workspace/manager.py` (updated -- `get_artifact_store()` helper)
- `backend/app/workflow/manager.py` (updated -- `datetime` import, `_persist_to_artifact_store()`, 7 wiring call sites)
- `backend/app/shared/enums/stage.py` (updated -- `TechLead`, `BugAnalyst` entries)
- `backend/app/agents/tech_lead.py` (NEW)
- `backend/app/agents/bug_analyst.py` (NEW)
- `backend/app/agents/factory.py` (updated -- imports + registrations)
- `backend/tests/test_phase2_agents.py` (NEW -- 23 tests)
- `backend/tests/test_v1_pipeline_fixes.py` (updated -- agent count snapshot)

**Tests:** `55 passed` (23 Phase 2 + 31 ArtifactStore + 1 endpoint) -- all green

**Full suite:** `527 passed, 8 pre-existing failures` (unchanged from before this session):
- 4x `UnicodeDecodeError` reading `engine.py`/`manager.py` without encoding -- pre-existing, not caused by this session
- 2x `FileStructurePlanner` DependencyGraph tests -- pre-existing
- 1x `PipelineResume` sanitizer test -- pre-existing
- 1x agent count (fixed in this session -- was 15, now 17)

**Commit:** `4d43132`

**Next:** Phase 2 remaining -- `SprintSupervisor` with feedback edges and retry gates

---

<!-- NEW LOG ENTRIES GO HERE -->

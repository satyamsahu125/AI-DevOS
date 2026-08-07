# AI DevOS — Pipeline Stage Flow

**Last Updated**: 2026-08-07
**Status**: Canonical stage sequence (verified from source)
**Authority**: `backend/app/workflow/workflow.json` + `pipeline_supervisor.py` + `manager.py`

---

## Overview

The pipeline has **3 phases**:

```
Phase 1 — DISCOVERY   (6 stages, sequential, once per project)
Phase 2 — SPRINT LOOP (5 stages per sprint, repeated for each sprint)
Phase 3 — RELEASE     (6 stages, sequential, once per project)
```

All phases execute through the same `execute → review → retry` cycle. Stages 7–8 in Phase 2
(BackendDeveloper + FrontendDeveloper) are the only stages that write source files to disk.

---

## Phase 1 — Discovery (6 stages)

Runs in `pipeline_supervisor._run_discovery()` via `get_discovery_stages()` (reads `workflow.json`).

| # | Stage | Agent | Produces | Gate |
|---|-------|-------|----------|------|
| 1 | StrategicReview | StrategicReviewAgent | Go/no-go viability assessment | — |
| 2 | ProductOwner | ProductOwnerAgent | Requirements + user stories | — |
| 3 | Architect | ArchitectAgent | Architecture: modules, APIs, data models | ⏸ Architecture review gate (human) |
| 4 | Designer | DesignerAgent | Design spec: pages, components, design system | ⏸ Design review gate (human) |
| 5 | Security | SecurityAgent | Security report: threats, mitigations | — |
| 6 | SprintPlanner | SprintPlannerAgent | Sprint plan: sprints, goals, feature assignments | — |

**Pre-discovery stages** (run via container — not through engine):
- **DomainResearch** — web/knowledge research before Q&A
- **Clarification** — interactive Q&A with user (⏸ Q&A gate)

**User gates in Discovery**:
- After Architect → `ARCHITECTURE_REVIEW_PENDING` (human approves or provides feedback)
- After Designer → `DESIGN_REVIEW_PENDING` (human approves or provides feedback)

**Designer is mobile-aware**: dispatches between web and mobile design system based on `project_type`.

---

## Phase 2 — Sprint Loop (5 stages × N sprints)

Runs in `manager._run_sprint()`, called for each sprint in `pipeline_supervisor._run_sprints()`.

| # | Stage | Agent | Produces | Notes |
|---|-------|-------|----------|-------|
| S1 | ScrumMaster | ScrumMasterAgent | Sprint task breakdown, user stories, agent assignments | Non-blocking: failure logs warning, sprint continues |
| S2 | FileStructurePlanner | FileStructurePlannerAgent | Concrete file list (path, module, purpose) | Blocking: failure aborts sprint |
| S3 | BackendDeveloper | BackendDeveloperAgent | **Real backend source files** (one LLM call per file) | Writes to `project/backend/` or project root (mobile) |
| S4 | FrontendDeveloper | FrontendDeveloperAgent | **Real frontend source files** (one LLM call per file) | Writes to `project/frontend/` or project root (mobile) |
| S5 | SprintDeploy | SprintDeployAgent | Sprint deployment / package verification | — |
| S6 | SprintReview | SprintReviewAgent | Sprint review notes + acceptance checks | — |

**Sprint execution order within each sprint**:
```
ScrumMaster → [rebuild context with scrum artifact] → FileStructurePlanner → BackendDeveloper → FrontendDeveloper → SprintDeploy → SprintReview
```

**ScrumMaster is per-sprint**: runs at the start of every sprint (Sprint 1, 2, …N) to produce
a fresh task breakdown for the current sprint's goals. The ScrumMaster artifact is then injected
into the context that FilePlanner and developer agents receive.

**FilePlanner is per-sprint**: runs after ScrumMaster each sprint. For Sprint 1 it initializes
the project structure (`project_writer.initialize_project()`).

**Mobile project type**: `WriteFrontendCodeAction` sets `area=""` for `mobile_app` projects so
all files write to the project root (not `project/frontend/`). `build_package_json` uses
`_RN_PKG_SIGNALS` to detect React Native and emit Expo-style `package.json`. DevOps prompt pins
Expo SDK 51.

**Sprint retry**: Each sprint gets up to 2 full attempts (`_run_sprint_with_retry(max_attempts=2)`).
After all sprints complete, `SprintMonitor` validates output (non-blocking).

---

## Phase 3 — Release (6 stages)

Runs in `pipeline_supervisor._run_release()` (reads `get_release_stages()` from `workflow.json`).

| # | Stage | Agent | Produces | Notes |
|---|-------|-------|----------|-------|
| R1 | Integration | IntegrationDeveloperAgent | Integration playbooks (Stripe, Auth, S3, Email) | — |
| R2 | QA | QAAgent | QA test plan, bug list, health score | — |
| R3 | BugAnalyst | BugAnalystAgent | Bug analysis from QA findings | — |
| R4 | DevOps | DevOpsAgent | Dockerfile, docker-compose, CI/CD, ops runbooks | Mobile-aware: Expo build for `mobile_app` |
| R5 | Document | DocumentAgent | Project documentation (README, API docs) | — |
| R6 | Retro | RetroAgent | Sprint retrospective, lessons learned | Pipeline terminates after this |

---

## Execute → Review → Retry Cycle

Every stage (all 3 phases) runs through the same cycle in `WorkflowEngine`:

```
Stage.Execute()
  ├─ Build prompt (ContextOrchestrator + PromptBuilder)
  ├─ Call LLM (OllamaProvider or BedrockProvider)
  ├─ Parse + validate output (action.run())
  ├─ Save artifact (ArtifactManager.save_artifact())
  └─→ Reviewer.review(artifact)
      ├─ AUTO_FIX  → apply mechanical fix, do NOT block
      ├─ ASK_HUMAN → block, inject feedback, retry (max 3)
      └─ FLAG      → note, do NOT block

  On approval:
    - Record trajectory (LearningLoop)
    - Embed in KnowledgeMemory
    - Write lesson (LessonStore)
    - Store predecessor message (MemoryManager)
    → NEXT STAGE

  On exhausted retries:
    - Stage FAILED → PipelineResult(success=False)
```

---

## Review Tiers

| Tier | Blocks? | Example |
|------|---------|---------|
| AUTO_FIX | No | "Empty section — auto-populated" |
| ASK_HUMAN | **Yes** | "Architecture doesn't cover security requirements" |
| FLAG | No | "Token count high — may retry" |

---

## Pipeline State Machine (24 states)

```
EMPTY → CLARIFYING → QA_PENDING ↔ QA_IN_PROGRESS
  → REQUIREMENTS_READY → ARCHITECTURE_READY → ARCHITECTURE_REVIEW_PENDING
  → DESIGN_READY → DESIGN_REVIEW_PENDING → DESIGN_APPROVED
  → SPRINT_PLAN_READY → SPRINT_PLAN_REVIEW_PENDING → SPRINT_IN_PROGRESS
  → SPRINT_COMPLETE → ALL_SPRINTS_COMPLETE
  → QA_COMPLETE → DEPLOYABLE → DONE

Change path:
  CHANGE_REQUESTED → RESUMING_FROM_CHANGE → SPRINT_IN_PROGRESS

Terminal: FAILED, PAUSED
```

States `AWAITING_HUMAN_APPROVAL`, `IMPACT_ANALYZED`, `REPLANNING` exist in the enum but
are not yet active in `WorkflowManager.run()`.

---

## Dependency Graph (from `impact_analyzer.py`)

Used by ImpactAnalyzer to determine which stages must be re-run when requirements change:

```
strategic_review
  → product_owner
    → architect
      → designer
      → security
        → sprint_planner
          → [per sprint]:
              scrum_master
                → file_planner
                  → backend  (+ security, architect)
                  → frontend (+ designer, architect)
          → [release]:
              qa → document → devops → retro
```

---

## File Output Paths

| Project type | Backend files | Frontend files |
|-------------|---------------|----------------|
| web_app (default) | `temp-workspace/{id}/project/backend/` | `temp-workspace/{id}/project/frontend/` |
| mobile_app | `temp-workspace/{id}/project/backend/` | `temp-workspace/{id}/project/` (root) |

Files named `_attempt_N_*` are automatically filtered from file listings and ZIP downloads.

---

## Auth + Project Isolation

Every pipeline stage and API endpoint enforces:
- **JWT auth**: `get_current_user` dependency on all project-scoped routes
- **Ownership**: `_assert_project_access(project, user)` — admins see all; users see only their own projects
- **Memory isolation**: all reads/writes keyed by `{project_id}:{key}`
- **Workspace isolation**: `temp-workspace/{project_id}/` per project

---

## For More Details

- **Stage implementation**: `backend/app/agents/` (agent classes)
- **Sprint execution**: `backend/app/workflow/manager.py::_run_sprint()`
- **Discovery execution**: `backend/app/workflow/pipeline_supervisor.py::_run_discovery()`
- **Dependency graph**: `backend/app/workflow/impact_analyzer.py::STAGE_DEPENDENCIES`
- **Workflow config**: `backend/app/workflow/workflow.json`
- **Review rules**: `backend/app/review/` (THREE_TIER review system)

# AI DevOS — Current Implementation State

_Last updated: 2026-08-07. Verified against actual source files — not aspirational plans._
_This document supersedes all earlier state descriptions for "what actually runs today."_

---

## 1. Objective

AI DevOS is a multi-agent software engineering pipeline. A user describes an application in plain
English; specialized AI agents (each backed by an LLM call, structured-output schema, and automated
reviewer) carry it from idea to a downloadable, runnable codebase.

---

## 2. High-level Architecture

```
Frontend (Vite + React 19 + TS, :5173)
  | Vite proxy -> localhost:8000 (no CORS config)
  v
Backend (FastAPI, :8000)
  +- DI Container (kernel/container.py)
  |    ~40 singletons; all wired in Container.build()
  +- PipelineSupervisor (workflow/pipeline_supervisor.py)
  |    3-phase orchestrator: Discovery → Sprint Loop → Release
  +- WorkflowManager (workflow/manager.py)
  |    State machine over 24 ProjectState values
  |    _run_sprint(): ScrumMaster → FilePlanner → Backend → Frontend → Deploy → Review
  +- WorkflowEngine (workflow/engine.py)
  |    execute -> review -> retry loop
  |    Injects: predecessor message, design context, lessons, patterns, intelligence context
  +- AgentFactory (agents/factory.py)
  |    17 agents registered; creates one per stage call
  +- LLMManager (llm/manager.py)
  |    OllamaProvider (default) or BedrockProvider; runtime-switchable
  +- Reviewer (review/reviewer.py)
  |    Three-tier: AUTO_FIX / ASK_HUMAN / FLAG
  +- Memory System (6 SQLite stores)
  +- Intelligence Layer (FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator)
  +- Auth Layer (JWT + RBAC; SQLite user store)
  |    get_current_user dependency on all project-scoped endpoints
  |    Per-user project isolation via owner_id
  +- EventBroadcaster -> WebSocket /ws/{project_id}
  +- CostTracker (per-call token/latency)
  +- SprintMonitor (cross-sprint context, output validation)
  +- ImpactAnalyzer (requirement change impact — stage + file level)
```

---

## 3. Component Status Table

### Backend Core

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| App entry | app/main.py | LIVE | lifespan wires broadcaster |
| DI Container | kernel/container.py | LIVE | ~40 singletons |
| PipelineSupervisor | workflow/pipeline_supervisor.py | LIVE | 3-phase orchestrator |
| WorkflowManager | workflow/manager.py | LIVE | full state machine + _run_sprint |
| WorkflowEngine | workflow/engine.py | LIVE | execute/review/retry |
| RetryPolicy | workflow/retry_policy.py | LIVE | configurable max_retries=3 |
| ImpactAnalyzer | workflow/impact_analyzer.py | LIVE | STAGE_DEPENDENCIES graph |
| DependencyGraph | workflow/dependency_graph.py | LIVE | STAGE_ORDER from workflow.json |

### Agents (17 registered in AgentFactory)

| Agent | Registration Key | Status | Phase |
|-------|----------------|--------|-------|
| StrategicReviewAgent | strategic_review | LIVE | Discovery |
| ProductOwnerAgent | product_owner | LIVE | Discovery |
| ArchitectAgent | architect | LIVE | Discovery |
| DesignerAgent | designer | LIVE | Discovery — mobile-aware |
| SecurityAgent | security | LIVE | Discovery |
| SprintPlannerAgent | sprint_planner | LIVE | Discovery |
| ScrumMasterAgent | scrum_master | LIVE | Sprint (first stage per sprint) |
| FileStructurePlannerAgent | file_planner | LIVE | Sprint (after ScrumMaster) |
| BackendDeveloperAgent | backend | LIVE | Sprint |
| FrontendDeveloperAgent | frontend | LIVE | Sprint — mobile-aware |
| SprintDeployAgent | sprint_deploy | LIVE | Sprint |
| SprintReviewAgent | sprint_review | LIVE | Sprint |
| IntegrationDeveloperAgent | integration | LIVE | Release |
| QAAgent | qa | LIVE | Release |
| BugAnalystAgent | bug_analyst | LIVE | Release |
| DevOpsAgent | devops | LIVE | Release — mobile-aware |
| DocumentAgent | document | LIVE | Release |
| RetroAgent | retro | LIVE | Release |
| ClarificationAgent | clarification | LIVE | Pre-discovery |
| DomainResearcherAgent | (via container only) | LIVE | Pre-discovery |
| ProductionDeployAgent | production_deploy | REGISTERED | Future release phase |
| ChatRouter | (via container only) | LIVE | Chat only |

### Auth Layer

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| JWT middleware | api/middleware/jwt_auth.py | LIVE | AUTH_ENABLED=true in .env |
| Auth endpoints | api/auth.py | LIVE | register, login, refresh, logout, /me, change-password |
| Admin endpoints | api/auth.py (admin_router) | LIVE | list/role/delete users — admin only |
| User store | db/users.py | LIVE | SQLite; bcrypt passwords; SHA-256 refresh tokens |
| Project ownership | shared/models/project.py | LIVE | owner_id field; defaults to "anonymous" |
| Ownership enforcement | api/project.py, workflow.py, files.py | LIVE | _assert_project_access on all routes |

### LLM Layer

| Component | Status | Notes |
|-----------|--------|-------|
| LLMManager | LIVE | runtime reconfigure via POST /settings/llm |
| OllamaProvider | LIVE | 600s timeout; /api/generate; /api/tags health |
| BedrockProvider | LIVE | Bearer-token auth; AWS Bedrock Runtime |
| CostTracker | LIVE | per-call token/latency; SQLite |

### Memory System

| Store | Status | Notes |
|-------|--------|-------|
| MemoryManager | LIVE | SQLite; project-scoped key-value |
| KnowledgeMemory | LIVE | HNSW vectors; semantic search |
| LearningLoop | LIVE | trajectory recording; per-project pattern retrieval |
| LessonStore | LIVE | human-readable lessons per stage/project |
| CheckpointManager | LIVE | crash recovery; reports incomplete sessions at startup |
| CostTracker | LIVE | token/latency tracking per call |
| ContextManager | DISABLED | not integrated in live pipeline |
| MemoryOrchestrator | DISABLED | name collision bug (self.store); disabled in container |

### Intelligence Layer

| Component | Status | Notes |
|-----------|--------|-------|
| FileIndexer | LIVE | db: backend/app/memory/file_index.db (hardcoded) |
| DependencyGraph | LIVE | built on FileIndexer |
| CodeSummarizer | LIVE | built on FileIndexer |
| ContextOrchestrator | LIVE | wired into WorkflowEngine; skips gracefully on error |
| SprintMonitor | LIVE | validate_sprint_output + generate_sprint_brief |
| ImpactAnalyzer | LIVE | stage-level + file-level impact analysis |

### API Layer

| Router | Status | Auth Required | Notes |
|--------|--------|---------------|-------|
| health | LIVE | No | GET /ready, GET /health |
| auth | LIVE | No | register, login, refresh, logout, /me |
| admin | LIVE | admin role | user management |
| project | LIVE | Yes (owner) | CRUD + files + metrics + sandbox |
| workflow | LIVE | Yes (owner) | start, design-review, sprint-plan, changes, continue, stop |
| gates | LIVE | Yes (owner) | architecture review gate |
| websocket | LIVE | No | /ws/{project_id} real-time events |
| chat | LIVE | Yes | ChatRouter |
| artifacts | LIVE | Yes | artifact retrieval |
| agents | LIVE | No | agent info |
| memory | LIVE | No | memory store access |
| learning | LIVE | No | learning stats |
| files | LIVE | Yes (owner) | file content + download + run-instructions |
| logs | LIVE | No | pipeline execution logs |
| settings | LIVE | No | LLM settings |
| intelligence | LIVE | No | file index, dependency graph |
| git | LIVE | No | git export |
| integrations | LIVE | No | integration playbooks |
| preview | LIVE | No | live app preview |
| analytics | LIVE | No | cost/usage analytics |

### Frontend

| Component | Status | Notes |
|-----------|--------|-------|
| App.tsx (router) | LIVE | / login signup /projects /projects/:id /settings /analytics /admin |
| LandingPage | LIVE | redirects to /projects if logged in |
| LoginPage | LIVE | email+password auth; register link |
| ProjectsPage | LIVE | dashboard + new project modal |
| WorkspacePage | LIVE | pipeline, chat, files, logs, artifacts, metrics, changes tabs |
| SettingsPage | LIVE | LLM settings |
| AnalyticsPage | LIVE | cost/usage dashboard |
| AdminPage | LIVE | user management (admin only) |
| AppLayout | LIVE | sidebar nav with all tabs |
| lib/auth.tsx | LIVE | JWT; access token in memory; refresh in sessionStorage |
| lib/api.ts | LIVE | typed client; all calls via /api prefix; Bearer token header |
| DesignReviewModal | LIVE | spec view + visual HTML preview (sandboxed iframe) |
| RequirementChangePanel | LIVE | analyze → confirm/cancel → history |
| Frontend tests | MISSING | no Jest/Vitest configured |

---

## 4. Pipeline State Machine (24 states)

```
EMPTY → CLARIFYING → QA_PENDING ↔ QA_IN_PROGRESS
  → REQUIREMENTS_READY → ARCHITECTURE_READY → ARCHITECTURE_REVIEW_PENDING
  → DESIGN_READY → DESIGN_REVIEW_PENDING → DESIGN_APPROVED
  → SPRINT_PLAN_READY → SPRINT_PLAN_REVIEW_PENDING → SPRINT_IN_PROGRESS
  → SPRINT_COMPLETE → ALL_SPRINTS_COMPLETE
  → QA_COMPLETE → DEPLOYABLE → DONE

Change path: CHANGE_REQUESTED → RESUMING_FROM_CHANGE → SPRINT_IN_PROGRESS
Terminal: FAILED, PAUSED
```

States `AWAITING_HUMAN_APPROVAL`, `IMPACT_ANALYZED`, `REPLANNING` exist in the enum
but are not active in `WorkflowManager.run()`.

---

## 5. Sprint Execution Order (per sprint)

```
_run_sprint(project_id, sprint):
  1. ScrumMaster      — task breakdown for this sprint (NON-BLOCKING)
  2. [rebuild context — ScrumMaster artifact now available]
  3. FileStructurePlanner — which files to create (BLOCKING)
  4. BackendDeveloper  — generate backend source files
  5. FrontendDeveloper — generate frontend source files
  6. SprintDeploy      — verify deployment artifacts
  7. SprintReview      — acceptance check + notes
  [after all sprints: SprintMonitor.validate_sprint_output (non-blocking)]
```

ScrumMaster failure only logs a warning — the sprint continues with sprint context alone.
FileStructurePlanner failure aborts the current sprint attempt.

---

## 6. Mobile Project Support

When `project_type == "mobile_app"`:
- **Designer**: uses `_MOBILE_ROLE_BRIEFING` (RN primitives, React Navigation, NativeWind, SafeAreaView, 44×44pt touch targets)
- **FrontendDeveloper**: uses `_MOBILE_ROLE_BRIEFING` (no `<div>`, no browser APIs, AsyncStorage, Expo SDK 51)
- **WriteFrontendCodeAction**: sets `area=""` — files write to project root (not `project/frontend/`)
- **build_package_json**: detects `_RN_PKG_SIGNALS` → emits Expo-style package.json with `"main": "node_modules/expo/AppEntry.js"` and Expo scripts
- **DevOps**: uses `_MOBILE_DEVOPS_PROMPT` — pins `sdkVersion: "51.0.0"` with CRITICAL RULE section

---

## 7. Known Issues and Limitations

| ID | Issue | Severity | Status |
|----|-------|---------|--------|
| N1 | Missing `transformers` in requirements.txt | HIGH | OPEN |
| N2 | Stale test: Fix009ScrumMasterInjection (2 tests) | MEDIUM | OPEN |
| N3 | Stale test: test_pipeline_runs_every_stage_in_order | MEDIUM | OPEN |
| N4 | ContextManager disabled | LOW | OPEN |
| N5 | MemoryOrchestrator name collision unresolved | LOW | OPEN |
| N6 | Hardcoded DB paths in container.py | LOW | OPEN |
| G1 | Zero frontend tests | HIGH | OPEN |
| G2 | No E2E / integration tests | HIGH | OPEN |
| G4 | Synchronous pipeline — no parallelism | MEDIUM | BY DESIGN |
| G5 | SQLite only — no multi-instance | MEDIUM | FUTURE |

---

## 8. Configuration

### config/config.yaml (default)
```yaml
llm:
  provider: ollama
  model: qwen2.5-coder:7b
  base_url: http://localhost:11434
  temperature: 0.1
  max_tokens: 4096
runtime:
  workspace: backend/temp-workspace
  retry_limit: 3
  log_level: INFO
```

### .env overrides
```
AUTH_ENABLED=true           # JWT auth enforced (default: true)
JWT_SECRET_KEY=<secret>     # Required when AUTH_ENABLED=true
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15

LLM_PROVIDER=bedrock        # or ollama
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
AWS_BEARER_TOKEN_BEDROCK=...
```

---

## 9. Test Status (last verified 2026-07-27)

- Total collected: 377 tests, 47 files
- Known failures: 4 (2 missing `transformers`, 2 stale test classes)
- Long suites excluded from quick run: test_sprint_sync, test_project_intelligence, test_project_file_generation

---

## 10. Running the System

```bash
# Prerequisites
ollama serve
ollama pull qwen2.5-coder:7b

# Backend
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

First run: register a user at `http://localhost:5173` → signup page.

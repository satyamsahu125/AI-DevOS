# Implementation Roadmap

**Last Updated**: 2026-08-07
**Current Version**: 2.0
**Test Count**: 377 collected / ~57 passing in subset run / 4 known failures

---

## COMPLETED (as of 2026-08-07)

### Core Pipeline
- 19-stage pipeline across 3 phases (Discovery → Sprint Loop × N → Release)
- All agents implemented and registered in AgentFactory
- WorkflowManager 24-state state machine (crash-safe)
- PipelineSupervisor: 3-phase orchestrator
- Three-tier review system (AUTO_FIX/ASK_HUMAN/FLAG) with detailed feedback injection
- Real code generation — Backend/Frontend write files to disk
- Crash-safe resume via ProjectState persistence + CheckpointManager
- Sprint retry (up to 2 full sprint attempts on failure)

### Sprint Architecture
- ScrumMaster now runs **per-sprint** as first step in `_run_sprint()` (before FileStructurePlanner)
- ScrumMaster is non-blocking — sprint continues on failure
- FileStructurePlanner consumes ScrumMaster artifact via rebuilt context
- Sprint order: ScrumMaster → FileStructurePlanner → Backend → Frontend → Deploy → Review

### Auth + Security
- JWT authentication (python-jose, HS256, 15min access token)
- Refresh token rotation (SHA-256 hash in SQLite, sessionStorage in frontend)
- RBAC: admin / developer / viewer roles
- Per-user project isolation (owner_id on Project model + list_by_owner + _assert_project_access)
- All project-scoped API endpoints auth-protected
- Mandatory frontend login (ProtectedRoute, no anonymous access)
- Auth toggle: AUTH_ENABLED=true (default)

### Mobile Support
- Designer stage: mobile-aware (`_MOBILE_ROLE_BRIEFING` for RN primitives)
- FrontendDeveloper stage: mobile-aware (no `<div>`, no browser APIs, Expo SDK 51)
- File output: mobile files write to project root (not `project/frontend/`)
- package.json: Expo-style for mobile (`build_package_json` detects `_RN_PKG_SIGNALS`)
- DevOps: `_MOBILE_DEVOPS_PROMPT` pins `sdkVersion: "51.0.0"`

### Memory System
- MemoryManager, KnowledgeMemory (HNSW), LearningLoop, LessonStore, CheckpointManager, CostTracker

### Intelligence Layer
- FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator
- SprintMonitor: cross-sprint context + sprint output validation
- ImpactAnalyzer: stage-level + file-level requirement change impact

### API Layer
- 20 sub-routers; all project-scoped routes protected
- WebSocket real-time events (multi-tab; thread-safe broadcaster)
- Design preview endpoint: generates self-contained HTML wireframe from DesignArtifact
- Download endpoint: ZIP with RUN_INSTRUCTIONS.md + VALIDATION_REPORT.md + VERIFICATION_REPORT.md

### Frontend
- React 19 + Vite 8 + TypeScript 6 + Tailwind v4
- Auth: login/register/logout, JWT + refresh token, protected routes
- WorkspacePage: pipeline / chat / files / logs / artifacts / metrics / changes tabs
- RequirementChangePanel: analyze → confirm/cancel → history
- DesignReviewModal: spec view + sandboxed HTML preview iframe
- Sidebar navigation: all workspace tabs + logout
- _attempt_ file filtering in file explorer

### Deployment
- R3: DevOps stage generates Dockerfile, docker-compose.yml, .github/CI
- R4: Git integration (GitManager, sprint commits, GitHub export)
- R5: Live preview (PreviewManager, subprocess server, UI iframe)
- R6: Integration agent (Stripe/Auth/S3/Email playbooks)
- R7: Analytics dashboard (CostTracker + LearningLoop data)
- R10: OpenTelemetry instrumentation (no-op when not configured)

---

## KNOWN ISSUES (open)

### Test Failures (4 tests, 2 root causes)

**1. MISSING: `transformers` in requirements.txt**
- Affects: test_designer_agent, test_v1_pipeline_fixes (pattern isolation test)
- Fix: Add `transformers>=4.0.0` to backend/requirements.txt
- Effort: 5 minutes

**2. STALE: Fix009ScrumMasterInjection (2 tests)**
- Affects: backend/tests/test_review_report_fixes.py
- Root cause: Tests create WorkflowManager without required `sprint_monitor` kwarg
- Fix: Update test setup to match current WorkflowManager constructor
- Effort: 30 minutes

**3. STALE: test_pipeline_runs_every_stage_in_order**
- Affects: backend/tests/test_v1_pipeline_fixes.py
- Root cause: Expected stage list doesn't account for FileStructurePlanner running inside sprint
- Fix: Update expected stage sequence to match current pipeline
- Effort: 30 minutes

### Disabled Components
- **ContextManager** — not integrated in live pipeline (commented out in container.py)
- **MemoryOrchestrator** — name collision bug (self.store attribute/method conflict); disabled

---

## NEXT (immediate priorities)

### Priority 1: Fix test suite (1 hour total)
1. Add `transformers>=4.0.0` to backend/requirements.txt
2. Fix Fix009ScrumMasterInjection tests
3. Fix test_pipeline_runs_every_stage_in_order

### Priority 2: Frontend testing ✅ COMPLETE
- Vitest 3 + React Testing Library 16 + jsdom installed
- `vitest.config.ts` separates test config from `vite.config.ts` (avoids Rolldown native binary load)
- 4 test files written, 0 TypeScript errors (`tsc --noEmit` clean):
  - `src/lib/auth.test.tsx` — hasRole, probe() 401/404/network/session-restore, login success+failure, logout
  - `src/App.test.tsx` — ProtectedRoute: loading spinner, unauth redirect, auth renders outlet, public routes
  - `src/pages/LoginPage.test.tsx` — form render, empty-field disable, login/register flow, error display, password mismatch
  - `src/pages/LandingPage.test.tsx` — no-crash render, redirect when logged in, loading no-redirect
- Run with: `cd frontend && npm test`

### Priority 3: Re-enable ContextManager
- Fix name collision in MemoryOrchestrator
- Wire ContextManager back into container.py

### Priority 4: E2E testing
- Playwright or Cypress E2E tests for full project creation → download flow

---

## FUTURE (medium term)

- **PostgreSQL migration** — replace SQLite for multi-instance support
- **Redis gate state** — distributed pipeline state for horizontal scaling
- **Celery/async workers** — parallelize independent pipeline stages
- **Frontend tests (extended)** — Vitest coverage for WorkspacePage tabs, ProjectsPage, API client
- **Admin dashboard** — project management for admins across all users
- **Rate limiting** — per-user API rate limits
- **Webhook notifications** — push events on pipeline completion

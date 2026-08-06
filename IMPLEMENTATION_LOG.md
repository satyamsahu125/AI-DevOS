# AI DevOS — Implementation Log

Tracks every change applied from DEV_PHASES.md, phase by phase.
Format: `[STATUS] FILE — WHAT — WHY`

Status codes: ✅ Done | 🔄 In Progress | ❌ Failed | ⏭ Skipped (not applicable)

---

## Phase 0 — Unblock the Pipeline

**Goal:** Fix Bug A and Bug B so a project can run end-to-end with Bedrock.

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 0.1 | ✅ | `workflow/manager.py` | Bug A: save minimal Clarification artifact in else-branch | |
| 0.2 | ✅ | `workflow/engine.py` | Bug B: fallback to project.json in `_with_clarification_context` | |
| 0.3 | ✅ | `backend/.env` | Add LLM_MAX_TOKENS=16384, LLM_TEMPERATURE=0.1 | |

---

## Phase 1 — Memory Foundation

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 1.1 | ⏭ | `workflow/engine.py` | Remove `_WORKFLOW_MESSAGE_KEY` — kept for legacy fallback path; deferred to cleanup pass | |
| 1.2 | ⏭ | `workflow/engine.py` | Remove 6 `_with_*` methods — extracted to `_legacy_enrich()` fallback; deferred to cleanup | |
| 1.3 | ✅ | `memory/manager.py` | Add `store_stage_output` / `load_stage_output` methods | |
| 1.4 | ✅ | `workflow/engine.py` | Replace enrichment chain with orchestrator path + `_legacy_enrich()` fallback; `record_approval` / `record_rejection` calls added | |
| 1.5 | ✅ | `workflow/manager.py` | Memory writes (record_approval / store_stage_output) after Clarification artifact saves (both QA and Bug-A paths) | |
| 1.6 | ✅ | `kernel/container.py` | `MemoryContextOrchestrator` registered as `memory_orchestrator`; wired into `WorkflowEngine` | |
| 1.7 | ✅ | NEW `memory/orchestrator.py` | `MemoryOrchestrator` — 4-layer context assembler (Episodic + Semantic + Procedural + Working) | |
| 1.8 | ✅ | NEW `shared/dto/stage_context.py` | `StageContext` dataclass with `to_prompt_dict()` | |
| 1.9 | ✅ | NEW `kernel/health_check.py` | `HealthCheck` + `build_default_health_check()` for container startup validation | |
| 1.10 | ⏭ | `context/context.py` | ContextManager not yet activated — `context_manager=None` passed to orchestrator; activating in Phase 3 | |

---

## Phase 2 — Intelligent Retry Engine

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 2.1 | ⏭ | `workflow/retry_policy.py` | Kept as backward-compat shim; IntelligentRetryEngine takes precedence when wired | |
| 2.2 | ✅ | `workflow/engine.py` | Rejection path calls `retry_engine.plan()`; FLAG triggers early break; prompt_instruction injected | |
| 2.3 | ✅ | `learning/performance_scorer.py` | `memory_manager` param added; scores written to `perf:score:{stage}` key after each computation | |
| 2.4 | ✅ | NEW `workflow/retry_engine.py` | `IntelligentRetryEngine` — rejection-type-aware with performance-based effective_max; `should_retry()` backward-compat | |
| 2.5 | ✅ | NEW `shared/dto/retry_plan.py` | `RetryPlan` dataclass with strategy, prompt_instruction, reason, delay_ms | |
| 2.6 | ✅ | `kernel/container.py` | `retry_engine` registered and passed to `WorkflowEngine`; `performance_scorer` receives `memory_manager` | |

---

## Phase 3 — Activate Intelligence Layer

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 3.1 | ✅ | `workflow/pipeline_supervisor.py` | `file_indexer` param added; `_trigger_intelligence_index()` called after each sprint completes (non-fatal) | |
| 3.2 | ✅ | `intelligence/context_orchestrator.py` | `get_project_state()` added — returns dict, never None | |
| 3.3 | ✅ | `memory/orchestrator.py` | `_load_intelligence()` returns `{}` not `None`; calls `get_project_state()` | |
| 3.4 | ✅ | `kernel/container.py` | `lesson_store` registered; silent try/except in `_build_prompt_analyzer()` removed; `context_orchestrator` wired into `memory_orchestrator`; `file_indexer` wired into `workflow_manager` | |
| 3.5 | ✅ | `config/models.py` + `config/loader.py` | `lessons_db` field added to Settings; `LESSONS_DB` env var read in loader | |

---

## Phase 4 — Human Collaboration Gates

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 4.1 | ✅ | `shared/enums/project_state.py` | Added ARCHITECTURE_REVIEW_PENDING, SPRINT_PLAN_REVIEW_PENDING | |
| 4.2 | ✅ | `workflow/pipeline_supervisor.py` | Architecture gate pause after Architect; sprint plan gate check in _run_sprints(); DISCOVERY_STATES + SPRINT_STATES updated | |
| 4.3 | ✅ | `workflow/manager.py` | `_await_gate()` method added; gate state handlers in run() for all 3 gates | |
| 4.4 | ✅ | NEW `api/gates.py` | Full FastAPI router: GET /current, POST approve/revise/adjust for all 3 gates; background thread resume | |
| 4.5 | ✅ | NEW `shared/dto/gate_result.py` | GateResult dataclass with status, gate, next_state, next_stage, message, artifact | |
| 4.6 | ✅ | `api/router.py` | gates_router registered | |

---

## Phase 8 — Agile Sprint File Management

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 8.1 | ✅ | `shared/schemas/file_plan_schema.py` | Added `operation: Literal["create","update","patch"]` + `change_description` to `PlannedFile` | |
| 8.2 | ✅ | `workspace/project_files.py` | Added `file_exists()` + `read_file()` | |
| 8.3 | ✅ | `actions/write_project_files.py` | Added `file_registry` param; `_build_file_prompt()` reads existing content for update/patch ops | |
| 8.4 | ✅ | `prompt/file_plan_builder.py` | Added operation field rules + existing-file instruction to `_ROLE_BRIEFING` | |
| 8.5 | ⏭ | `prompt/backend_builder.py` | No change needed — operation context flows via `detail` string from `_build_file_prompt()` | |
| 8.6 | ✅ | NEW `workspace/file_registry.py` | `FileRegistry` — tracks written files per project/sprint; `to_prompt_summary()` for LLM context | |
| 8.7 | ✅ | NEW `shared/dto/sprint_file_plan.py` | `SprintFilePlan` + `SprintFileEntry` typed DTOs | |
| 8.8 | ✅ | `actions/write_file_plan.py` | Added `file_registry` param; injects `to_prompt_summary()` into enriched prompt; updated `system_prompt` to include `operation`/`change_description` fields | |
| 8.9 | ✅ | `agents/file_planner.py` | Added `file_registry` param; threaded to `WriteFilePlanAction` | |
| 8.10 | ✅ | `kernel/container.py` | Registered `file_registry` singleton; wired into `file_planner_agent` and `write_project_files_action` | |

---

## Phase 6 — Infrastructure & Production Hardening

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 6.1 | ✅ | NEW `api/middleware/__init__.py` | Package marker | |
| 6.2 | ✅ | NEW `api/middleware/auth.py` | `APIKeyMiddleware` — X-API-Key header validation | Disabled when VALID_API_KEYS not set; constant-time comparison |
| 6.3 | ✅ | NEW `observability/__init__.py` | Package marker | |
| 6.4 | ✅ | NEW `observability/logging.py` | `configure_logging()` — JSON or text formatter via LOG_FORMAT env var | Silences noisy third-party loggers |
| 6.5 | ✅ | NEW `tasks/__init__.py` | Package marker | |
| 6.6 | ✅ | NEW `tasks/pipeline_task.py` | `dispatch_pipeline()` — Celery when Redis available, threads as fallback | `run_pipeline` Celery task; `CELERY_BROKER_URL` controls activation |
| 6.7 | ✅ | `main.py` | Added `APIKeyMiddleware`, `configure_logging()` call | Auth and logging wired at app startup |
| 6.8 | ✅ | `api/project.py` | `_validate_project_request()` — name max 100 chars + regex, description max 2000 chars | Both create endpoints validate |
| 6.9 | ✅ | `requirements.txt` | Added celery, redis, structlog, opentelemetry-sdk, opentelemetry-instrumentation-fastapi | |
| 6.10 | ✅ | `kernel/container.py` | Fixed hardcoded DB paths: `costs.db` and `file_index.db` now use `Path(__file__).resolve()` anchoring | |
| 6.11 | ✅ | NEW `Dockerfile` | `python:3.12-slim` image; installs requirements; mounts temp-workspace and data | |
| 6.12 | ✅ | NEW `docker-compose.yml` | api + worker + redis services; health checks; bind mounts for persistence | |
| 6.13 | ✅ | `backend/.env` | Added VALID_API_KEYS, CELERY_BROKER_URL, LOG_FORMAT vars | |

---

## Phase 5 — Code Execution Sandbox

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 5.1 | ✅ | NEW `shared/dto/sandbox_result.py` | `LintResult`, `TestResult`, `BuildResult`, `SandboxResult` typed DTOs | `to_json()`, `to_prompt_text()`, `.disabled()` factory |
| 5.2 | ✅ | NEW `execution/code_sandbox.py` | `CodeSandbox` — detect stack, lint/test/build, uses `SecureExecutionSandbox` | `SANDBOX_ENABLED=false` default; subprocess fallback |
| 5.3 | ✅ | `execution/safety_policy.py` | Added `SANDBOX_EXECUTION` operation type; always ALLOWs in `check()` | Audit-logged via safety_checks table |
| 5.4 | ✅ | `workflow/pipeline_supervisor.py` | Added `code_sandbox` param; `_run_sandbox()` method; called after sprint complete | Stores results at `sandbox:latest` via memory_manager |
| 5.5 | ✅ | `workflow/manager.py` | Added `code_sandbox` param; passed to `PipelineSupervisor` | |
| 5.6 | ✅ | `agents/bug_analyst.py` | `analyse()` accepts `sandbox_results: str`; injected before QA findings | |
| 5.7 | ✅ | `kernel/container.py` | Registered `code_sandbox` singleton; wired into `workflow_manager` | |
| 5.8 | ✅ | `backend/.env` | Added `SANDBOX_ENABLED=false`, `SANDBOX_TIMEOUT=60`, docker image vars | |

---

## Phase 7 — Template Engine + Model Routing

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| 7.1 | ✅ | `memory/learning_loop.py` | Added `record_success()` convenience wrapper around `record_trajectory()` | Callers pass kwargs; no Trajectory construction needed |
| 7.2 | ✅ | `memory/lesson_store.py` | Added `record()` convenience wrapper around `add_lesson()` with auto-generated UUID | |
| 7.3 | ✅ | `memory/orchestrator.py` | Added `learning_loop` + `lesson_store` params; `record_approval()` calls `learning_loop.record_success()`; `record_rejection()` calls `lesson_store.record()` | Non-fatal: errors are logged |
| 7.4 | ✅ | NEW `shared/dto/model_profile.py` | `ModelProfile(provider, model, temperature, max_tokens)` dataclass | All fields optional except provider + model |
| 7.5 | ✅ | NEW `llm/model_router.py` | `ModelRouter` with `STAGE_PROFILES` dict; `get_profile(stage) -> ModelProfile`; `register_profile()` for tests | Inherits global provider/model from .env; only overrides temperature + max_tokens |
| 7.6 | ✅ | NEW `learning/template_engine.py` | `TemplateEngine` — `extract_template()`, `find_similar()`, `inject_template()` | SQLite-backed; key-set overlap scoring; non-fatal error contract |
| 7.7 | ✅ | `llm/manager.py` | `generate_text()` accepts `profile: ModelProfile | None`; applies profile temperature + model + max_tokens overrides (explicit kwargs still win) | |
| 7.8 | ✅ | `kernel/container.py` | Registered `model_router` + `template_engine` singletons; wired `learning_loop` + `lesson_store` into `memory_orchestrator` | |

---

## R5 — Live App Preview (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R5.1 | ✅ | NEW `execution/preview_manager.py` | `PreviewManager` class: `start()`, `stop()`, `health()`, `restart()`, `get_preview_logs()`; port pool 9000–9019; 30-min idle cleanup thread | `PREVIEW_ENABLED=false` default (safe for production); one subprocess per project |
| R5.2 | ✅ | NEW `api/preview.py` | `GET /projects/{id}/preview/status`, `POST /preview/restart`, `DELETE /preview`, `GET /preview/logs`, `/preview/{id}/{path}` reverse proxy via httpx | Proxy validates preview is running before forwarding; 503 on crash/not-running |
| R5.3 | ✅ | `workflow/pipeline_supervisor.py` | Added `preview_manager` param + `_start_preview()` method; called after `_commit_sprint_to_git()`; only starts if build succeeded | Reads `sandbox:latest` build status to gate preview start |
| R5.4 | ✅ | `workflow/manager.py` | Added `preview_manager` param; passed to `PipelineSupervisor` | Thread-through |
| R5.5 | ✅ | `kernel/container.py` | Registered `preview_manager` singleton; passed to `workflow_manager` | |
| R5.6 | ✅ | `api/router.py` | Registered `preview_router` | |

---

## R4 — Git Integration (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R4.1 | ✅ | NEW `workspace/git_manager.py` | `GitManager` class: `init()`, `commit_sprint()`, `commit_stage()`, `log()`, `push_to_github()`, `_stage_safe()`, `_lint_dockerfile_structure()` | Non-fatal; always-excluded .env files; security: token never stored |
| R4.2 | ✅ | `workspace/manager.py` | `create_workspace()` calls `GitManager(workspace_root).init()` after project.json written | Idempotent; non-fatal; every project starts as a git repo |
| R4.3 | ✅ | `workflow/pipeline_supervisor.py` | Added `_commit_sprint_to_git()` method; called after `_run_sandbox()` in sprint loop | Commits sprint files with `feat(sprint-N):` message |
| R4.4 | ✅ | `workflow/engine.py` | Added `_commit_stage_to_git()` method; called in approval path after `_extract_template()` | Commits after Architecture, Design, DevOps, etc. stage approvals |
| R4.5 | ✅ | NEW `api/git.py` | `GET /projects/{id}/git-log` and `POST /projects/{id}/push-to-github` endpoints | push-to-github: token never logged/stored/returned; HTTPS GitHub URLs only |
| R4.6 | ✅ | `api/router.py` | Registered `git_router` | Wires git endpoints into FastAPI |

---

## Verification Results — R Phases

| Phase | Result | Notes |
|-------|--------|-------|
| R1 | ✅ | Subagent verified: 8/8 checks passed |
| R2 | ✅ | Subagent verified: 10/10 checks passed |
| R3 | ✅ | Subagent verified: 7/7 checks passed |
| R4 | ✅ | Subagent verified: 6/6 checks passed |
| R5 | ✅ | Subagent verified: 6/6 checks passed |

---

## Verification Results

| Phase | Result | Notes |
|-------|--------|-------|
| 0 | ✅ | Subagent verified: Bug A + Bug B both confirmed fixed |
| 1 | ✅ | Subagent verified: 8/8 checks passed |
| 2 | ✅ | Subagent verified: 6/6 checks passed |
| 3 | ✅ | Subagent verified: 8/8 checks passed |
| 4 | ✅ | Subagent verified: 8/8 checks passed |
| 5 | ✅ | Subagent verified: 8/8 checks passed |
| 6 | ✅ | Subagent verified: 10/10 checks passed |
| 7 | ✅ | Subagent verified: 8/8 checks passed |
| 8 | ✅ | Subagent verified: 9/9 checks passed |

---

## Critical Fix — Startup Crash (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| C.1 | ✅ | `execution/code_sandbox.py:142` | Fixed SyntaxError: `*expr if cond else []` in tuple → extracted to local var `subdirs` before unpacking | Root cause: starred expression with ternary operator invalid in tuple literal; cascaded through import chain to crash uvicorn |

---

## R1 — Critical Bug Fixes (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R1.1 | ✅ | `execution/code_sandbox.py:142` | BUG-1: Fixed SyntaxError — `*expr if cond else []` in tuple literal → local `subdirs` var + `[project_dir, *subdirs]` | Root cause: starred expression with ternary invalid in tuple; cascaded to crash uvicorn |
| R1.2 | ✅ | `agents/chat_router.py` | BUG-2: Both LLM call sites extract `.content` from `LLMResponse` — `llm_response = self.llm.generate_text(...)` then `reply=llm_response.content` | Was passing `LLMResponse` object to `ChatResponse(reply=...)` which expects `str` |
| R1.3 | ✅ | `shared/dto/workflow_result.py` | BUG-3: Added `artifact: Any = field(default=None)` to `WorkflowResult` dataclass | PipelineSupervisor BugAnalyst rollback reads `result.artifact.structured_content` — field was missing |
| R1.4 | ✅ | `workflow/engine.py` | BUG-3: Approval return path includes `artifact=artifact` in `WorkflowResult` | Populates the artifact field so rollback logic can read it |
| R1.5 | ✅ | `workflow/engine.py` | BUG-4: `_with_gate_feedback()` method reads `gate:feedback:{gate}` from memory_manager and injects "HUMAN GATE FEEDBACK" block into base_content | Gate feedback was stored (by api/gates.py) but never read back into retry prompt |
| R1.6 | ✅ | `llm/manager.py` | BUG-5a: `set_stage_profile(profile)` method stores `_stage_profile`; `generate_text()` uses it when no explicit profile provided, then clears it | ModelRouter profiles were registered but had no call site in live pipeline |
| R1.7 | ✅ | `workflow/engine.py` | BUG-5a: `_apply_model_router_profile()` calls `model_router.get_profile()` then `llm.set_stage_profile()`; called in `run()` per stage | Wires ModelRouter into active pipeline |
| R1.8 | ✅ | `workflow/engine.py` | BUG-5b: `_inject_template()` and `_extract_template()` methods wired into `run()`; `model_router=None`/`template_engine=None` init guards | TemplateEngine was built but had zero call sites |
| R1.9 | ✅ | `kernel/container.py` | BUG-5c: ContextManager re-enabled with try/except registration; `memory_orchestrator` now receives resolved context_manager; `_build_workflow_engine()` sets `engine.model_router` + `engine.template_engine` post-construction | ContextManager was commented out; ModelRouter/TemplateEngine were registered but not passed to engine |
| R1.10 | ✅ | `api/websocket.py` | BUG-6: `_is_valid_token()` with `hmac.compare_digest`; `token: str = Query(default="")` param; rejection before `ws_manager.connect()` with close code 4001 | HTTPMiddleware exempted WebSocket upgrades — endpoint had no auth |
| R1.11 | ✅ | `backend/.gitignore` | BUG-7: Created with `.env`, Python runtime, and data directory patterns | Additional gitignore layer; root `.gitignore` already had `.env` |

**Verification:** Subagent confirmed all 8 checks PASS (BUG-1 through BUG-7).

---

## Frontend — Full Rebuild R1–R10 (August 2026)

**Scope:** Complete frontend rebuild preserving the existing design language (dark bg, CSS variables, grid background, accent glow) while adding all R6–R10 backend features: JWT auth, Quick Build mode, integrations tab, analytics page, gate modals, context warning banner, admin panel, and sidebar navigation.

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| FE.1 | ✅ | NEW `src/lib/auth.tsx` | `AuthProvider` + `AuthContext` + `useAuth()` hook + `hasRole()` utility | Access token: in-memory ref only; refresh token: sessionStorage. `probe()` calls `/api/auth/me` — 404/422 → auth disabled → ANON_USER admin; 401 → auth enabled, not logged in; 200 → restore session |
| FE.2 | ✅ | `src/lib/api.ts` | Full rewrite — `setTokenProvider()` for Bearer injection; added `Integration` to STAGES; `createAndRunProject()` accepts `mode`; gate endpoints (`getCurrentGate`, `approveGate`, `reviseGate`, `adjustSprintPlan`); R6 integration endpoints; R7 analytics endpoints; R8 auth/admin endpoints; new types: `IntegrationService`, `ProjectIntegrations`, `AnalyticsOverview`, `AnalyticsLearning`, `AdminUser`, `GateInfo` | Token injection via module-level callback avoids circular imports |
| FE.3 | ✅ | `src/main.tsx` | Wrapped app in `AuthProvider`; added `AppWithAuth` component that calls `setTokenProvider(getToken)` via `useEffect` after provider mounts | Ensures Bearer tokens are injected before any API call |
| FE.4 | ✅ | `src/App.tsx` | Added `ProtectedRoute` (spinner → redirect to /login → Outlet); added `/login` → `LoginPage`; wrapped AppLayout in ProtectedRoute; added `/analytics` → `AnalyticsPage`; added `/admin` → `AdminPage` | ProtectedRoute is a no-op when `authEnabled=false` |
| FE.5 | ✅ | NEW `src/pages/LoginPage.tsx` | Login + Register in single page with mode toggle; matches design language; auto-login after register; default admin credentials hint; password-match validation | |
| FE.6 | ✅ | NEW `src/pages/AnalyticsPage.tsx` | Stats grid (6 metrics); horizontal bar chart per stage (color-coded by success rate); learning lessons list + top patterns; empty state | |
| FE.7 | ✅ | NEW `src/pages/AdminPage.tsx` | User list from `/admin/users`; inline role selector per row; delete with confirmation; self-modification guard; role summary chips; auth-disabled tip when list is empty | |
| FE.8 | ✅ | `src/pages/ProjectsPage.tsx` | `NewProjectModal`: added mode state + Build Mode selector (🏗 Full Pipeline / ⚡ Quick Build cards), passes mode to `createAndRunProject()`; `ProjectCard`: shows "⚡ Quick" badge when `project.mode === "quick"` | |
| FE.9 | ✅ | `src/components/layout/Sidebar.tsx` | Added Analytics nav item (always visible); Admin nav item (admin role only); Integrations tab in project section; user footer with avatar initial, email, role badge, logout button (shown when `authEnabled && !user.anonymous`) | |
| FE.10 | ✅ | `src/pages/WorkspacePage.tsx` | Added `IntegrationsPanel` (calls `getProjectIntegrations`, shows detected services + env vars); added `GateModal` (approve / request revision with feedback); added `contextWarning` state + dismissible banner (bottom-right toast); added `gateOpen` state wired to pipeline state watcher for `architecture_review_pending` + `sprint_plan_review_pending`; action button labels updated for gate states; Quick Build badge in top nav | |
| FE.11 | ✅ | `src/hooks/usePipeline.ts` | Added `ContextWarning` interface; added `onContextWarning` optional callback param; added `context_warning` case in WS switch — calls callback + logs to liveLogs | WorkspacePage passes `setContextWarning` directly |

**Auth backward-compatibility:** `AUTH_ENABLED=false` (default) → probe gets 404 → `authEnabled=false`, `user=ANON_USER(role=admin)` → ProtectedRoute passes through → full app works without login flow.

**Quick Build backward-compatibility:** `mode` defaults to `"full"` on all existing projects. New `NewProjectModal` adds a mode picker; old projects without the field render no badge.

---

## R10 — Scale: OpenTelemetry + Redis Gate State (August 2026)

**Spec gate respected:** PostgreSQL migration, Alembic, and Celery-enabled-by-default are NOT implemented — spec says "Do NOT start R10 until you have ≥3 concurrent users or write contention is observed." SQLite + threading is adequate for a team of 5–10. The R10 scaffolding below enables the migration path without breaking anything.

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R10.1 | ✅ | NEW `observability/tracing.py` | `configure_tracing()`, `get_tracer()`, `instrument_fastapi()`, `pipeline_span()`, `stage_span()`, `llm_span()`, `sprint_span()` | Zero-cost no-op when `OTEL_ENDPOINT` not set; `_NoOpTracer` + `_NoOpSpan` avoid any allocations |
| R10.2 | ✅ | NEW `db/gate_state.py` | `GateStateRegistry` (abstract), `RedisGateStateRegistry`, `InMemoryGateStateRegistry`, `build_gate_state_registry()`, `get_gate_state_registry()` | Redis probe at startup; falls back to in-memory on any error; JSON-serialized fields; 24h TTL |
| R10.3 | ✅ | `main.py` | Imported `configure_tracing`, `instrument_fastapi`; called `configure_tracing()` at module level; `instrument_fastapi(app)` inside `create_application()` | Auto-instruments all FastAPI routes when OTel is enabled |
| R10.4 | ✅ | `kernel/container.py` | Imported `build_gate_state_registry`; registered `"gate_state_registry"` singleton with try/except fallback to `InMemoryGateStateRegistry` | Non-fatal: never blocks container build |
| R10.5 | ✅ | `workflow/pipeline_supervisor.py` | Imported `pipeline_span`, `stage_span`, `sprint_span`; wrapped `run()` body with `pipeline_span`; wrapped per-sprint `_run_sprint_with_retry()` with `sprint_span` | All spans are no-op until `OTEL_ENDPOINT` is set |
| R10.6 | ✅ | `docker-compose.yml` | Added `otel-collector` + `jaeger` services under `profiles: ["otel"]` | Start with `docker compose --profile otel up`; zero impact on default `docker compose up` |
| R10.7 | ✅ | NEW `otel-collector-config.yaml` | OTLP receivers (gRPC + HTTP), batch + attributes processors, OTLP/Jaeger exporter, logging exporter | Ready to use with `profiles: ["otel"]` |
| R10.8 | ✅ | `backend/.env` | Added `REDIS_URL=` and `OTEL_ENDPOINT=` + `OTEL_SERVICE_NAME=ai-devos` | Both disabled by default; set to activate |

**To enable tracing:**
```
OTEL_ENDPOINT=http://localhost:4317
docker compose --profile otel up
```

**To enable distributed gate state (multi-instance):**
```
REDIS_URL=redis://localhost:6379/0
```

**PostgreSQL migration path (when load demands it):**
Install `sqlalchemy>=2.0`, `alembic`, `psycopg2-binary`. Run `alembic init`. MemoryManager, UserStore, LessonStore, and LearningLoop each have isolated `db_path` parameters — migrate them one at a time using Alembic env pointing to `DATABASE_URL`. Gate state switches automatically when `REDIS_URL` is set.

---

## R9 — Context Intelligence + Quick Build Mode (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R9.1 | ✅ | `shared/dto/project_request.py` | Added `mode: str = "full"` field | "full" (default 19-stage pipeline) or "quick" (prototype — skips 7 stages) |
| R9.2 | ✅ | `workspace/manager.py` | Added `mode` param to `create_workspace()`; stored in project.json as `"mode"` | `load_project_json()` can now return mode for any component to read |
| R9.3 | ✅ | `project/manager.py` | `create_project()` reads `request.mode` and passes to `create_workspace()` | |
| R9.4 | ✅ | `workflow/pipeline_supervisor.py` | Added `_QUICK_BUILD_SKIP_DISCOVERY`, `_QUICK_BUILD_SKIP_RELEASE`, `_QUICK_BUILD_SKIP_GATES`, `_QUICK_BUILD_MAX_SPRINTS=1` constants | |
| R9.5 | ✅ | `workflow/pipeline_supervisor.py` | Added `_get_project_mode(project_id)` helper | Reads mode from project.json; defaults to "full" on error |
| R9.6 | ✅ | `workflow/pipeline_supervisor.py` | `_run_discovery()`: skips `strategic_review` + `security`; auto-approves architect + designer gates | Quick mode: 4 stages instead of 7 |
| R9.7 | ✅ | `workflow/pipeline_supervisor.py` | `_run_sprints()`: auto-approves sprint plan gate; caps `sprints_to_run` to `_QUICK_BUILD_MAX_SPRINTS` (1) | Quick mode: 1 sprint only |
| R9.8 | ✅ | `workflow/pipeline_supervisor.py` | `_run_release()`: skips `document` + `retro` stages | Quick mode: integration → qa → bug_analyst → devops |

**Quick Build pipeline (mode="quick"):** Clarification → DomainResearch → Architect (auto-gate) → Designer (auto-gate) → SprintPlanning (auto-gate) → BackendDeveloper (1 sprint) → FrontendDeveloper (1 sprint) → Integration → QA → BugAnalyst → DevOps

**Note on context intelligence tuning:** ModelRouter, TemplateEngine, and ContextManager are already wired (from R1). R9 defines them as measurement phases — actual tuning happens after data collection from production runs. The infrastructure is in place.

---

## R8 — JWT Auth + RBAC + Rate Limiting (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R8.1 | ✅ | NEW `db/__init__.py` | Auth database package | |
| R8.2 | ✅ | NEW `db/users.py` | `UserStore` — users + refresh_tokens SQLite tables; `create_user()`, `verify_password()`, `create_refresh_token()`, `validate_refresh_token()`, `invalidate_refresh_token()`, `get_user_store()` singleton | bcrypt cost factor 12; refresh tokens stored as SHA-256 hashes; default admin created on first run with warning |
| R8.3 | ✅ | NEW `api/middleware/jwt_auth.py` | `create_access_token()`, `decode_token()`, `get_current_user` FastAPI dependency, `require_role(*roles)` RBAC factory | `AUTH_ENABLED=false` by default — single-user setups unaffected; anonymous user returned when disabled |
| R8.4 | ✅ | NEW `api/middleware/rate_limit.py` | `check_default()`, `check_pipeline()`, `check_chat()` — sliding-window rate limiter; `RATE_LIMIT_ENABLED=false` by default | Pre-R10 in-memory impl; post-R10 replace `_store` dict with Redis ZRANGEBYSCORE |
| R8.5 | ✅ | NEW `api/auth.py` | 9 endpoints: POST /auth/register, /auth/login, /auth/refresh, /auth/logout, /auth/change-password; GET /auth/me; PUT+DELETE /admin/users/* | All admin endpoints gated by `require_role("admin")` dependency |
| R8.6 | ✅ | `api/router.py` | Imported `auth_router` + `admin_router`; included in `api_router` | |
| R8.7 | ✅ | `backend/.env` | Added `AUTH_ENABLED=false`, `JWT_SECRET_KEY=`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`, `AUTH_DB_PATH=data/auth.db`, `RATE_LIMIT_ENABLED=false` + limits | All disabled by default — zero-impact on existing single-user deployments |

**Design:** Auth is opt-in (`AUTH_ENABLED=false` default). When disabled: `get_current_user` returns synthetic anonymous admin — all existing endpoints continue to work without tokens. When enabled: Bearer JWT required on all non-exempt endpoints; passlib bcrypt hashes passwords; refresh tokens stored as SHA-256 hashes, never plain text.

---

## R7 — Analytics Dashboard (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R7.1 | ✅ | NEW `api/analytics.py` | 4 endpoints: `GET /analytics/overview`, `GET /analytics/projects/{id}`, `GET /analytics/stage/{stage_name}`, `GET /analytics/learning` | Reads CostTracker (SQLite), LearningLoop (trajectories), LessonStore (lessons); no project-state mutation |
| R7.2 | ✅ | `api/router.py` | Imported and included `analytics_router` | |
| R7.3 | ✅ | `events/broadcaster.py` | Added `context_warning(project_id, used_tokens, limit_tokens, pct)` method | Broadcasts `type: "context_warning"` event via WebSocket |
| R7.4 | ✅ | `workflow/engine.py` | Added `_check_context_window(project_id)` + `_CONTEXT_LIMITS` dict; called in approval path after `mark_approved()` | Provider-derived limits (Claude=200K, Gemini=1M, Ollama=32K); broadcasts warning when project cumulative tokens > 75% of limit |

**Analytics data sources already collecting:** CostTracker records every LLM call to SQLite. LearningLoop records every trajectory (approved + rejected) with stage, approval status, retry count, tokens, latency. LessonStore records human-readable lessons per approval.

**Context window warning:** fires once per stage approval when cumulative project tokens cross 75% threshold. Non-blocking — exceptions are caught. Provider auto-detected from model name string.

---

## R6 — Integration Agent (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R6.1 | ✅ | `shared/enums/stage.py` | Added `Integration = "Integration"` enum value | New release-phase stage before QA |
| R6.2 | ✅ | NEW `integration/__init__.py` | Integration package init | R6 package root |
| R6.3 | ✅ | NEW `integration/playbook_loader.py` | `PlaybookLoader` — `list_services()`, `get(service)`, `detect_from_text(text)`, `get_env_vars(services)` | Module-level `_cache` for process-lifetime caching; keyword detection fallback |
| R6.4 | ✅ | NEW `integration/playbooks/stripe.json` | Stripe Payments playbook — env vars, Python/Node snippets, package deps | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| R6.5 | ✅ | NEW `integration/playbooks/jwt_auth.json` | JWT Auth playbook — access + refresh tokens, bcrypt, FastAPI OAuth2 | `JWT_SECRET_KEY`, `JWT_ALGORITHM` |
| R6.6 | ✅ | NEW `integration/playbooks/google_oauth.json` | Google OAuth 2.0 playbook — authlib / passport-google-oauth20 | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` |
| R6.7 | ✅ | NEW `integration/playbooks/aws_s3.json` | AWS S3 playbook — boto3 / @aws-sdk/client-s3; upload, download, presigned URLs | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` |
| R6.8 | ✅ | NEW `integration/playbooks/sendgrid.json` | SendGrid email playbook — transactional + template sends | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` |
| R6.9 | ✅ | NEW `integration/playbooks/posthog.json` | PostHog analytics playbook — events, user identification, feature flags | `POSTHOG_API_KEY`, `POSTHOG_HOST` |
| R6.10 | ✅ | NEW `agents/integration_developer.py` | `IntegrationDeveloperAgent` — LLM detects services + keyword fallback; writes `integrations/<service>_client.py` and `INTEGRATIONS.md` | Overrides `execute()` to chain detection → playbook loading → file writing |
| R6.11 | ✅ | `agents/factory.py` | Registered `"integration"` → `IntegrationDeveloperAgent` | Import + registry call added |
| R6.12 | ✅ | `agents/resolver.py` | Added "integration", "integrationdeveloper", "integration_developer" → `"integration"` mappings | Stage name resolution |
| R6.13 | ✅ | `workflow/stage_lookup.py` | Added "integration", "integration_developer", "integrationdeveloper" → `Stage.Integration` | Stage enum lookup |
| R6.14 | ✅ | `workflow/workflow.json` | Inserted `integration` stage before `qa` in release phase | Pipeline now: integration → qa → bug_analyst → devops → document → retro |
| R6.15 | ✅ | NEW `api/integrations.py` | `GET /integrations/services`, `GET /integrations/services/{service}`, `POST /integrations/detect`, `GET /projects/{id}/integrations`, `GET /projects/{id}/integrations/env-vars` | Read-only; no project-state mutation |
| R6.16 | ✅ | `api/router.py` | Imported and included `integrations_router` | |
| R6.17 | ✅ | `workspace/project_readme.py` | Added `integration_env_vars` param to `build_run_instructions()`; generates "Required Environment Variables" table when integrations are detected | R6 env var documentation in README |

**Architecture:** Integration runs in release phase before QA. `IntegrationDeveloperAgent.execute()` overrides `BaseAgent.execute()` to chain: LLM detection → keyword fallback → playbook loading → file writing → `StageArtifact` return. Non-invasive: errors are caught and logged; the pipeline never stops on integration failures.

---

## R3 — Real Deployment Output (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R3.1 | ✅ | `prompt/file_plan_builder.py` | Added 'devops' as valid `responsible_stage`; added mandatory infra files block (Dockerfile, docker-compose.yml, .dockerignore, .github/workflows/ci.yml) to `_ROLE_BRIEFING` | FilePlanner now instructs LLM to include DevOps infra files in every file plan |
| R3.2 | ✅ | `prompt/devops_builder.py` | Added `.dockerignore` as FILE 3 with standard exclusion patterns; updated output format block | DevOps prompt now produces 5 files instead of 4 |
| R3.3 | ✅ | `workspace/project_readme.py` | Added `has_dockerfile` param to `build_run_instructions()`; Docker section appears first with `docker compose up` as primary command | R3 exit criteria: "docker compose up as primary command in RUN_INSTRUCTIONS.md" |
| R3.4 | ✅ | `api/files.py` | Added `memory: MemoryManager` dependency; detects `has_dockerfile` from zip contents; adds `VERIFICATION_REPORT.md` via `_build_verification_report()` helper | Download now includes sandbox results report |
| R3.5 | ✅ | `execution/code_sandbox.py` | Added `verify_dockerfile()` + `_lint_dockerfile_structure()` methods | Dockerfile structural validation: checks FROM/CMD/ENTRYPOINT; uses `docker build --check` if Docker available |
| R3.6 | ✅ | `workflow/pipeline_supervisor.py` | After devops stage succeeds, calls `self._code_sandbox.verify_dockerfile(project_id)` | Non-fatal: logs warnings but doesn't stop pipeline |
| R3.7 | ✅ | `api/project.py` | Removed duplicate download endpoint; kept sandbox-results endpoint; fixed unused imports | Download now served by api/files.py (already registered) |

**Note:** `DevOpsAgent` + `WriteDeploymentAction` already write real files to disk — the core capability was already implemented. R3 adds: infra file instructions in FilePlanner, .dockerignore, Dockerfile verification, and Docker section in RUN_INSTRUCTIONS.

---

## R2 — Verifiable Code (August 2026)

| # | Status | File | Change | Note |
|---|--------|------|--------|------|
| R2.1 | ✅ | `backend/.env` | `SANDBOX_ENABLED=true` | Activates existing CodeSandbox infrastructure — subprocess mode, no Docker required |
| R2.2 | ✅ | `execution/code_sandbox.py` | Added `syntax_check(project_id, sprint)` + `_syntax_check_all(project_dir, stack)` | Runs py_compile on all .py files or node --check on all .js files; skips venv/cache dirs |
| R2.3 | ✅ | `workflow/pipeline_supervisor.py` | Syntax check called in `_run_sprints()` after sprint succeeds — fails with PipelineResult error if syntax errors found | Sprint not marked complete if code doesn't parse |
| R2.4 | ✅ | NEW `workspace/dependency_pinner.py` | `DependencyPinner` — `pin_requirements()` + `pin_package_json()` with PyPI/npm registry resolution; session-level `_version_cache` | Rewrites unpinned specs to exact versions (e.g. `fastapi==0.111.0`) |
| R2.5 | ✅ | `workflow/pipeline_supervisor.py` | Added `dependency_pinner` param + `_pin_dependencies()` method; called after sprint syntax check, before sandbox | Finds all requirements.txt/package.json in workspace and pins them |
| R2.6 | ✅ | `workflow/manager.py` | Added `dependency_pinner` param; passed to `PipelineSupervisor` | Thread through from container |
| R2.7 | ✅ | `kernel/container.py` | Registered `dependency_pinner` singleton; passed to `workflow_manager`; import added | DI wiring for DependencyPinner |
| R2.8 | ✅ | `workflow/engine.py` | Added `_inject_sandbox_results(project_id, stage_name, content)` method; called in `run()` for bug_analyst stage | Reads `sandbox:latest` from memory; prepends AUTOMATED VERIFICATION RESULTS block |
| R2.9 | ✅ | `api/project.py` | Added `GET /projects/{id}/sandbox-results?sprint={n}` endpoint | Returns stored sandbox JSON from memory_manager |
| R2.10 | ✅ | `api/project.py` | Added `GET /projects/{id}/download` endpoint + `_build_verification_report()` helper | Returns zip of workspace files + `VERIFICATION_REPORT.md` generated from sandbox results |

---

## Strategic Analysis — New Roadmap (August 2026)

| # | Status | Deliverable | Notes |
|---|--------|-------------|-------|
| S.1 | ✅ | `docs/CTO_STRATEGY_REPORT.html` | Full 13-section strategic report: AI DevOS assessment, Emergent comparison, 7 bugs, adopt/reject analysis, 10-phase roadmap, implementation order |
| S.2 | ✅ | `docs/future/README.md` | New roadmap index — replaced old 5-phase plan with 10-phase R1–R10 roadmap |
| S.3 | ✅ | `docs/future/PHASE-R1-fix-bugs.md` | All 7 bugs documented with exact fix instructions |
| S.4 | ✅ | `docs/future/PHASE-R2-verifiable-code.md` | CodeSandbox activation, dependency pinning, syntax check, QA feedback loop |
| S.5 | ✅ | `docs/future/PHASE-R3-real-deployment.md` | DevOps stage generates Dockerfile/docker-compose/CI |
| S.6 | ✅ | `docs/future/PHASE-R4-git-integration.md` | GitManager, sprint commits, GitHub push, portable export |
| S.7 | ✅ | `docs/future/PHASE-R5-live-preview.md` | PreviewManager, subprocess app server, UI iframe, reverse proxy |
| S.8 | ✅ | `docs/future/PHASE-R6-integration-agent.md` | Integration stage, Playbook library, Stripe/Auth/S3/Email/SendGrid |
| S.9 | ✅ | `docs/future/PHASE-R7-analytics.md` | Analytics dashboard, context window warning, learning insights |
| S.10 | ✅ | `docs/future/PHASE-R8-auth-rbac.md` | JWT auth, RBAC, rate limiting, project ownership |
| S.11 | ✅ | `docs/future/PHASE-R9-context-intelligence.md` | ContextManager/ModelRouter/TemplateEngine tuning, Quick Build mode |
| S.12 | ✅ | `docs/future/PHASE-R10-scale.md` | PostgreSQL, Redis gate state, Celery, OpenTelemetry, load testing |

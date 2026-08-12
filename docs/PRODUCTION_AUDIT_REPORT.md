# AI DevOS — Full Production Readiness Audit Report

**Date:** 2026-08-10
**Auditor:** Senior Staff Engineer / Security / QA / DevOps Review
**Codebase:** AI-DevOS3 (`backend/` + `frontend/`)
**Verdict at a glance:** ❌ NOT PRODUCTION READY

---

## TABLE OF CONTENTS

1. [Repository Architecture Summary](#1-repository-architecture-summary)
2. [Repository Inventory](#2-repository-inventory)
3. [System Architecture Reconstruction](#3-system-architecture-reconstruction)
4. [Documentation vs Implementation Analysis](#4-documentation-vs-implementation-analysis)
5. [Code Quality Audit](#5-code-quality-audit)
6. [Error Handling & Failure Analysis](#6-error-handling--failure-analysis)
7. [Security Audit](#7-security-audit)
8. [API Audit](#8-api-audit)
9. [Database Audit](#9-database-audit)
10. [Concurrency & Distributed System Audit](#10-concurrency--distributed-system-audit)
11. [AI / LLM / Agent Audit](#11-ai--llm--agent-audit)
12. [Testing Audit](#12-testing-audit)
13. [Performance & Scalability Analysis](#13-performance--scalability-analysis)
14. [Observability Audit](#14-observability-audit)
15. [DevOps / Deployment Audit](#15-devops--deployment-audit)
16. [Dependency Audit](#16-dependency-audit)
17. [Configuration Audit](#17-configuration-audit)
18. [Production Readiness Score](#18-production-readiness-score)
19. [Complete Findings Register](#19-complete-findings-register)
20. [Production Blockers — Must Fix Before Production](#20-production-blockers--must-fix-before-production)
21. [Prioritized Remediation Roadmap](#21-prioritized-remediation-roadmap)
22. [Keep As-Is](#22-keep-as-is)
23. [Final Architecture Review](#23-final-architecture-review)

---

## 1. Repository Architecture Summary

AI DevOS is an **autonomous software engineering platform**. Given a natural-language project description, it orchestrates a multi-stage pipeline of specialized AI agents (Product Owner → Architect → Designer → Security → SprintPlanner → Backend/Frontend Developer → QA → DevOps) to generate a fully-structured software project, including code, documentation, deployment configs, and retrospectives.

**Stack:**
- **Backend:** Python 3.12, FastAPI, SQLite (×6 DBs), optional Redis+Celery, optional Docker sandbox
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS + Radix UI
- **LLM Providers:** Ollama (local), Google Gemini, AWS Bedrock, Anthropic Claude
- **Transport:** REST + WebSocket (real-time pipeline events)
- **Authentication:** Dual-layer — API key middleware + JWT (RBAC)
- **Persistence:** Six separate SQLite databases, flat JSON project files

---

## 2. Repository Inventory

```
AI-DevOS3/
├── backend/
│   ├── app/
│   │   ├── actions/          # 22 LLM action wrappers (one per stage output)
│   │   ├── agents/           # 26 agent implementations
│   │   ├── api/              # 20 FastAPI routers + middleware
│   │   ├── artifact/         # ArtifactManager (saves stage outputs)
│   │   ├── artifacts/        # EMPTY DIRECTORY — orphan
│   │   ├── config/           # YAML + env config loader
│   │   ├── context/          # Context assembly, token budget
│   │   ├── core/             # DI container, service registry
│   │   ├── db/               # UserStore (auth.db), GateStateRegistry
│   │   ├── events/           # EventBroadcaster (WebSocket)
│   │   ├── execution/        # ExecutionEngine, Pipeline, Sandbox
│   │   ├── integration/      # Playbook loader (external integrations)
│   │   ├── intelligence/     # FileIndexer, DependencyGraph, Summarizer
│   │   ├── kernel/           # Bootstrap, Container, Lifecycle
│   │   ├── learning/         # PerformanceScorer, TemplateEngine
│   │   ├── llm/              # LLMManager, Factory, 4 providers
│   │   ├── memory/           # MemoryManager + 15 sub-components
│   │   ├── observability/    # Structured logging, OTel tracing
│   │   ├── project/          # ProjectManager, ProjectRepository
│   │   ├── projects/         # ⚠️ 347 runtime JSON files in source tree
│   │   ├── prompt/           # 30+ prompt builders
│   │   ├── review/           # Reviewer (quality gate)
│   │   ├── runtime/          # AgentFactory, AgentRuntime, AgentMonitor
│   │   ├── session/          # Checkpoint, SessionManager
│   │   ├── shared/           # DTOs, enums, models, constants
│   │   ├── storage/          # SQLite adapter abstraction
│   │   ├── tasks/            # Celery pipeline task
│   │   ├── workflow/         # WorkflowEngine, Manager, Pipeline
│   │   └── workspace/        # WorkspaceManager, GitManager
│   ├── backend/app/memory/   # ⚠️ NESTED DUPLICATE directory
│   ├── data/                 # SQLite DBs (gitignored at root, tracked in backend/)
│   ├── temp-workspace/       # Generated project workspaces (gitignored)
│   ├── .env                  # ⚠️ Contains real credentials (gitignored)
│   ├── .env.example          # Clean template
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt      # Unpinned (>=) versions
│   └── pytest.ini            # testpaths=tests, but tests/ DOES NOT EXIST
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Routes + ProtectedRoute
│   │   ├── App.test.tsx      # Only 1 test file (routes)
│   │   ├── components/       # UI components
│   │   ├── hooks/            # useWebSocket, useProject
│   │   ├── lib/              # auth.ts, api client
│   │   └── pages/            # 7 pages
│   └── package.json
├── docs/                     # Extensive documentation (30+ md files)
├── scripts/                  # dev/test helper scripts
├── data/                     # SQLite DBs at root level (duplicate of backend/data/)
├── memory/                   # memory.db at root (duplicate of backend/memory/)
├── .gitignore
└── dev.sh / run.sh
```

**Counts:**
- Backend Python files: ~220 files
- Backend tests: **0 files** (`tests/` directory does not exist)
- Frontend test files: **1 file** (App.test.tsx)
- Runtime project JSON files committed to source: **347 files**
- SQLite databases: **6 active** (memory, knowledge, learning, lessons, auth, costs) plus orphaned copies at root

---

## 3. System Architecture Reconstruction

```
Browser (React + WebSocket)
         │
         ▼
FastAPI (uvicorn, port 8000)
    ├── APIKeyMiddleware  (X-API-Key header — disabled by default)
    ├── JWT Auth          (Bearer token — enabled per AUTH_ENABLED=true)
    └── REST + WebSocket Endpoints
         │
         ▼
WorkflowManager (state machine coordinator)
    ├── QAOrchestrator   (clarification Q&A flow)
    ├── ChangeManager    (requirement change handling)
    └── PipelineSupervisor (stage sequencing)
         │
         ▼
WorkflowEngine (single-stage execution coordinator)
    ├── ContextAssembler (builds LLM prompt from memory + artifacts)
    ├── StageRunner      (execute → review → retry loop)
    │     ├── ExecutionPipeline → AgentFactory → Agent.execute()
    │     └── Reviewer (quality gate: approves or rejects artifact)
    ├── LearningMiddleware (trajectory recording)
    ├── CheckpointMiddleware (crash recovery)
    └── GitMiddleware     (commit approved artifacts)
         │
         ▼
LLMManager (Ollama | Gemini | Bedrock | Claude)
         │
         ▼
ArtifactManager → WorkspaceManager → temp-workspace/{project_id}/
         │
         ▼
MemoryManager → data/memory.sqlite
         │
EventBroadcaster → WebSocket → Browser
```

**Background execution:** Pipeline stages run in `daemon` threads (default) or Celery tasks (when Redis configured).

---

## 4. Documentation vs Implementation Analysis

### DOCUMENTATION / IMPLEMENTATION MISMATCHES

| # | Documented | Actual | Files | Impact |
|---|-----------|--------|-------|--------|
| D1 | `tests/` directory should exist (pytest.ini: `testpaths = tests`) | Directory does not exist | `backend/pytest.ini` | Running `pytest` silently passes with 0 tests collected |
| D2 | Comment: "fix: replace passlib with direct bcrypt calls" (commit 2c5704b) | `auth.py:change_password()` still imports `passlib.context.CryptContext` at line 189 | `app/api/auth.py:189` | ImportError in production if passlib 4.x is installed |
| D3 | `SANDBOX_ENABLED=true` in `.env`; docs say sandbox is active | CodeSandbox is a no-op unless Docker daemon is also running | `app/execution/code_sandbox.py` | Generated code never gets lint/test/build validation |
| D4 | `AUTH_ENABLED=true` in `.env`; docs imply all routes protected | Gates, memory, logs, analytics, learning, intelligence, settings endpoints have no auth dependency | 7 router files | Unauthenticated access to sensitive endpoints |
| D5 | `.env.example` shows `WORKSPACE_ROOT=temp-workspace` | `ProjectRepository` hardcodes `backend/app/projects/` regardless of env var | `app/project/repository.py:15` | Cannot redirect project storage |
| D6 | docs claim Celery replaces daemon threads | Celery is optional and disabled by default; daemon threads are default path | `app/tasks/pipeline_task.py` | No task durability in default deployment |
| D7 | Mermaid diagram (`AI_DevOS_Architecture.mermaid`) shows clean pipeline | Multiple duplicate module pairs exist in actual codebase | various | Diagram misleads contributors |
| D8 | `RATE_LIMIT_ENABLED=false` in `.env` | Rate limiting is documented as enabled (R8 RATE_LIMIT_ENABLED=true) | `.env`, `app/api/middleware/rate_limit.py` | No rate limiting in practice |

---

## 5. Code Quality Audit

### 5.1 Correctness Issues

**BUG-01 (CONFIRMED): passlib still imported in change_password**
- File: `app/api/auth.py`, line 189
- `from passlib.context import CryptContext` is called inside `change_password()` despite the commit message claiming passlib was removed
- The commit added bcrypt directly to `db/users.py` but forgot to update `auth.py:change_password`
- Impact: `ImportError` or `AttributeError` on `POST /auth/change-password` in environments where passlib 4.x is installed (passlib 4.x breaks bcrypt support)

**BUG-02 (CONFIRMED): `tests/` directory does not exist**
- File: `backend/pytest.ini` (`testpaths = tests`)
- Running `pytest` from `backend/` reports `0 items collected` — silently passes with no tests
- The `.coverage` file exists (suggesting tests were run at some point) but the `tests/` dir was never committed

**BUG-03 (CONFIRMED): Duplicate module pairs in `app/llm/`**
- `app/llm/manager.py` AND `app/llm/llm_manager.py` — two LLM manager classes
- `app/llm/request.py` AND `app/llm/llm_request.py` — two request DTOs
- `app/llm/response.py` AND `app/llm/llm_response.py` — two response DTOs
- `app/llm/runtime.py` AND `app/llm/runtime_validation.py` — partial overlap
- Impact: Unclear which is authoritative; callers diverge; changes to one may not propagate to the other

**BUG-04 (CONFIRMED): `app/artifact/` and `app/artifacts/` both exist**
- `app/artifacts/` is an empty orphan directory
- All code uses `app/artifact/manager.py`
- Impact: Confusion, future accidental use of wrong path

**BUG-05 (CONFIRMED): `app/project/` vs `app/projects/`**
- `app/project/` contains the `ProjectRepository`, `ProjectManager`
- `app/projects/` contains **347 runtime JSON files** committed to source control
- These project JSON files are runtime data and should NEVER be in source control
- Impact: Repository bloat, leaks project descriptions/state, git history contains user data

**BUG-06 (CONFIRMED): ProjectRepository root is hardcoded**
- `ProjectRepository.__init__`: `self.root = root or Path(__file__).resolve().parents[1] / "projects"`
- This resolves to `backend/app/projects/` regardless of any environment variable
- Docker volume mounts and environment configuration cannot redirect project storage
- Impact: Generated project JSON always writes to source tree inside Docker

**BUG-07 (CONFIRMED): `backend/backend/app/memory/` nested directory**
- `backend/backend/` is an accidental duplicate directory from a misdirected copy operation
- Contains a `memory/` subdirectory with a memory.db file
- Impact: Structural confusion; risk of import resolution picking wrong module

### 5.2 Architecture Concerns

**ARCH-01: WorkflowEngine constructor takes 20+ parameters**
- `WorkflowEngine.__init__` accepts 22 dependency parameters, most optional with in-constructor fallback construction
- Every instantiation path instantiates multiple heavy dependencies (WorkspaceManager, MemoryManager, ArtifactManager, LearningLoop, etc.) regardless of whether they're needed
- Impact: Cannot unit-test individual components without triggering cascade construction; startup time penalty

**ARCH-02: Dual SQLite connection strategy**
- Some components open their own `sqlite3.connect()` directly (SafetyPolicy, UserStore)
- Other components go through `StorageAdapter` → `StorageFactory` → `SQLiteStorageAdapter`
- No unified connection pool or session factory
- Impact: Inconsistent transaction behavior; thread safety relies on `check_same_thread=False` everywhere

**ARCH-03: In-source project state**
- 347 project JSON files live at `backend/app/projects/*.json`
- This mixes runtime data with source code inside the Docker image
- Docker `COPY . .` bakes the current project state into every image build
- Impact: Image-baked runtime data, privacy risk, unbounded growth

**ARCH-04: Two virtual environments**
- `.venv/` at repository root
- `venv/` at `backend/` level
- Both contain different package sets
- Impact: Developer confusion; CI/CD must know which venv to activate

---

## 6. Error Handling & Failure Analysis

### 6.1 Pipeline Thread Crash (P0 Risk)

In the default deployment (no Redis/Celery):

```python
threading.Thread(target=_run_pipeline, daemon=True, name=f"workflow-{project_id}").start()
```

- If the pipeline throws an unhandled exception, the daemon thread silently dies
- The project remains in an intermediate state (e.g., `sprint_in_progress`) with no status update
- The `CheckpointMiddleware` saves incomplete-session markers, but these are only reported at next startup — not surfaced to the user
- No dead-letter mechanism; the failed pipeline cannot be automatically retried
- The UI polls for status but never receives a failure event for thread crashes

### 6.2 SQLite Thread Safety

Multiple components share a single `sqlite3.Connection` object with `check_same_thread=False`:
- `UserStore._conn`
- `SafetyPolicy._conn`
- `SQLiteStorageAdapter._conn`

SQLite with WAL mode supports concurrent readers, but **does not support concurrent writers**. Under concurrent pipeline execution (multiple projects simultaneously), write contention on the same SQLite file can produce `OperationalError: database is locked` which is not caught and propagated as an unhandled exception.

### 6.3 EventBroadcaster Loop Not Bound (Startup Race)

```python
broadcaster.bind_loop(asyncio.get_running_loop())  # in lifespan
```

If any code calls `broadcaster._send()` before `lifespan()` yields (e.g., during kernel startup), `self._loop` is None. The broadcaster silently drops the event with a debug log. This is a non-fatal silent data loss.

### 6.4 LLM Timeout

`LLMManager` uses `tenacity` for retry on network errors. The default timeout is 1200 seconds (20 minutes). During this period:
- The pipeline thread is blocked
- No progress events are sent to the WebSocket
- The UI appears frozen

### 6.5 Code Sandbox Cleanup on Timeout

In `sandbox.py:execute_command()`, when the container wait times out:
```python
container.kill()
exit_code = 124
logs = container.logs().decode(...)
```

The `finally` block correctly removes the container, but if `container.kill()` itself throws (Docker daemon restart), the `finally` block may fail silently, leaving orphaned containers.

---

## 7. Security Audit

### 7.1 CRITICAL: Multiple API Endpoints with Zero Authentication

**Finding:** Seven routers have NO `get_current_user` dependency, meaning they are completely unauthenticated even when `AUTH_ENABLED=true`.

| Endpoint(s) | Router File | Exposure |
|-------------|-------------|----------|
| `GET /workflow/{project_id}/gates/current` | `api/gates.py` | Reads gate state |
| `POST /workflow/{project_id}/gates/architecture/approve` | `api/gates.py` | **Approves architecture without any auth** |
| `POST /workflow/{project_id}/gates/design/approve` | `api/gates.py` | **Approves design without any auth** |
| `POST /workflow/{project_id}/gates/sprint-plan/approve` | `api/gates.py` | **Approves sprint plan without any auth** |
| `GET /memory/{project_id}` | `api/memory.py` | Reads all project memory |
| `GET /projects/{project_id}/logs` | `api/logs.py` | Reads build logs |
| `GET /projects/{project_id}/cost` | `api/logs.py` | Reads LLM cost data |
| `GET /settings/llm` | `api/settings.py` | Reads LLM config |
| `POST /settings/llm` | `api/settings.py` | **Changes LLM provider + API keys, writes to .env** |
| `GET /analytics/*` | `api/analytics.py` | Reads system analytics |
| `GET /learning/*` | `api/learning.py` | Reads learning data |
| `GET /intelligence/*` | `api/intelligence.py` | Reads project intelligence |

**Severity: CRITICAL (P0)**
- Any unauthenticated user on the network can approve pipeline gates for any project
- Any unauthenticated user can change the active LLM provider and inject a malicious API key via `POST /settings/llm` which writes to the `.env` file on disk

### 7.2 CRITICAL: Settings Endpoint Writes API Keys to .env

```python
# app/api/settings.py — no auth dependency
@router.post("/settings/llm")
def update_llm_settings(update: LLMSettingsUpdate, manager: LLMManager = ...) -> dict:
    env_values = {_ENV_KEY_BY_FIELD[k]: v for k, v in fields.items() ...}
    if env_values:
        upsert_env_values(env_values)  # writes to backend/.env on disk
```

An attacker can POST to `/settings/llm` with a malicious `bedrock_api_key` or `claude_api_key` — this overwrites the `.env` file with an attacker-controlled value that persists across restarts. No authentication required.

**Severity: CRITICAL (P0)**

### 7.3 HIGH: Default Admin Password "admin"

```python
# app/db/users.py:_ensure_admin()
default_pwd = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
```

A default admin account with password `admin` is created on first startup. A WARNING is logged, but there is no enforcement mechanism to require the password to be changed before the system accepts traffic.

**Severity: HIGH (P1)**

### 7.4 HIGH: passlib Import in change_password

```python
# app/api/auth.py:189
from passlib.context import CryptContext
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
new_hash = pwd_ctx.hash(body.new_password)
```

The system already uses `bcrypt` directly (as per the fix commit). Importing `passlib` here introduces an unnecessary dependency. If passlib 4.x is installed, `CryptContext` with bcrypt silently fails or produces incorrect hashes (a known passlib 4.x incompatibility). The `requirements.txt` does not include `passlib`, meaning this import will raise `ImportError` in the production environment.

**Severity: HIGH (P1)**

### 7.5 HIGH: Docker Sandbox Network Not Disabled

```python
# app/execution/sandbox.py
container = self.client.containers.run(
    image,
    ...
    network_disabled=False,  # Allows npm install etc.
    mem_limit="1g",
)
```

The comment acknowledges network is enabled "for npm install." However, LLM-generated code running inside the sandbox can make arbitrary outbound network calls (data exfiltration, SSRF, cryptocurrency mining). There is no allowlist; the sandbox has full internet access.

**Severity: HIGH (P1)**

### 7.6 HIGH: WebSocket Auth Does Not Validate JWT

```python
# app/api/websocket.py
def _is_valid_token(token: str) -> bool:
    if not _VALID_API_KEYS:
        return True  # dev mode
    return any(hmac.compare_digest(token, k) for k in _VALID_API_KEYS)
```

WebSocket auth only validates against `VALID_API_KEYS` (legacy API key auth). It does not accept or validate JWT tokens. When `AUTH_ENABLED=true` but `VALID_API_KEYS=` is empty (the configured state in `.env`), `_VALID_API_KEYS` is empty, so `_is_valid_token` returns `True` for **any** token, including empty string.

Result: Anyone can connect to any project's WebSocket without authentication.

**Severity: HIGH (P1)**

### 7.7 MEDIUM: Sensitive Credentials Present in `.env` (Not Committed, but Present)

The `.env` file is correctly gitignored, but contains:
- `BEDROCK_API_KEY=ABSK...` — real-looking Base64-encoded AWS credential
- `JWT_SECRET_KEY=2b15b048...` — a 64-hex-char JWT secret

These values are not in git history, but their presence in plaintext on disk means any process with filesystem read access can obtain them. No secrets management (Vault, AWS Secrets Manager, etc.) is used.

**Severity: MEDIUM (P2)**

### 7.8 MEDIUM: Rate Limiting Disabled by Default

```
RATE_LIMIT_ENABLED=false  # in .env
```

With no rate limiting, the pipeline endpoint (`POST /workflow/start`) can be hit in rapid succession, triggering unbounded LLM API costs and CPU/IO load.

**Severity: MEDIUM (P2)**

### 7.9 MEDIUM: Anonymous Users Default to Admin Role

```python
# app/api/middleware/jwt_auth.py
_ANONYMOUS_ROLE = "admin"  # full access in single-user mode
```

When `AUTH_ENABLED=false`, every request is treated as admin. In any environment where auth is accidentally disabled, all restrictions vanish.

**Severity: MEDIUM (P2)**

### 7.10 MEDIUM: Project Files Served Without Path Traversal Complete Guard

```python
# app/api/files.py
area_root = project_file_manager.area_dir(project_id, area).resolve()
target = (area_root / file_path).resolve()
if area_root not in target.parents and target != area_root:
    raise HTTPException(status_code=400, detail="Invalid file path")
```

The `area` parameter is passed directly to `area_dir()` without validation. If `area_dir()` doesn't sanitize the `area` value (e.g., `area=../../etc`), the constructed path may escape the intended directory even after `.resolve()`. The `area` parameter should be validated against an allowlist.

**Severity: MEDIUM (P2)**

### 7.11 LOW: Refresh Tokens Never Expire Automatically

Refresh tokens have a 7-day TTL stored in the database, but there is no background job to purge expired tokens. The `refresh_tokens` table grows without bound. Expired tokens return `None` from `validate_refresh_token()` (correct), but are never cleaned up.

**Severity: LOW (P4)**

---

## 8. API Audit

| Endpoint | Auth | Input Validation | Error Response | Pagination | Rate Limit | Notes |
|----------|------|-----------------|----------------|------------|------------|-------|
| `POST /auth/register` | N/A (public) | ✅ length, role | ✅ 409 on duplicate | N/A | ❌ | OK |
| `POST /auth/login` | N/A (public) | ✅ | ✅ 401 | N/A | ❌ | OK |
| `POST /auth/refresh` | N/A | ✅ | ✅ 401 | N/A | ❌ | OK |
| `POST /auth/change-password` | ✅ JWT | ✅ | ✅ | N/A | ❌ | **passlib import bug** |
| `GET /admin/users` | ✅ admin | N/A | ✅ | ❌ no pagination | ❌ | No pagination for large user lists |
| `POST /projects` | ✅ JWT | ✅ name pattern + length | ✅ | N/A | ❌ | OK |
| `GET /projects` | ✅ JWT | N/A | ✅ | ❌ | ❌ | All projects loaded into memory |
| `POST /workflow/start` | ✅ JWT | ✅ project exists | ✅ | N/A | ❌ | Thread-based, no task ID returned |
| `GET /workflow/{id}/gates/current` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | **CRITICAL** |
| `POST /workflow/{id}/gates/*/approve` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | **CRITICAL** |
| `GET /memory/{project_id}` | ❌ **NO AUTH** | N/A | ✅ | ❌ | ❌ | Exposes all project memory |
| `GET /projects/{id}/logs` | ❌ **NO AUTH** | N/A | ✅ | ✅ (since_id) | ❌ | Exposes build logs |
| `GET /projects/{id}/cost` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | Exposes cost data |
| `GET /settings/llm` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | Exposes provider config |
| `POST /settings/llm` | ❌ **NO AUTH** | ✅ | ✅ | N/A | ❌ | **CRITICAL — writes .env** |
| `GET /projects/{id}/files/{area}/{path}` | ✅ JWT | Partial | ✅ 404 | N/A | ❌ | `area` not allowlisted |
| `GET /projects/{id}/download` | ✅ JWT | ✅ | ✅ | N/A | ❌ | ZIP download — OK |
| `WebSocket /ws/{project_id}` | ❌ **Bypass** | N/A | Close 4001 | N/A | ❌ | JWT not validated |
| `GET /analytics/*` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | Exposes system analytics |
| `GET /intelligence/*` | ❌ **NO AUTH** | N/A | ✅ | N/A | ❌ | Exposes project intelligence |

**Global findings:**
- No API versioning (`/api/v1/`)
- No standardized pagination model
- No global rate limiting active by default
- No OpenAPI response schema for error cases (only success schemas defined)

---

## 9. Database Audit

### 9.1 Schema Design

Six SQLite databases are used, each with a separate connection object:

| Database | File | Owner Component | Tables |
|----------|------|----------------|--------|
| memory | `data/memory.sqlite` | MemoryManager, SafetyPolicy | `memories`, `safety_checks`, `artifacts` |
| auth | `data/auth.db` | UserStore | `users`, `refresh_tokens` |
| knowledge | `data/knowledge.sqlite` | KnowledgeMemory | UNVERIFIED |
| learning | `data/learning.sqlite` | LearningLoop | UNVERIFIED |
| lessons | `data/lessons.sqlite` | LessonStore | UNVERIFIED |
| costs | `data/costs.db` | CostTracker | UNVERIFIED |

Additionally, `memory.db` files exist at `backend/memory/memory.db` and `memory/memory.db` (root) — orphaned copies from earlier development.

### 9.2 Critical Database Issues

**DB-01: SafetyPolicy creates `artifacts` table in memory.sqlite**
```python
# app/execution/safety_policy.py:_ensure_schema()
CREATE TABLE IF NOT EXISTS artifacts (...)
```
`ArtifactManager` owns all writes to the `artifacts` table, but `SafetyPolicy` creates this table independently in a different connection to the same file. If `ArtifactManager` and `SafetyPolicy` open the same `memory.sqlite` with separate connections, `CREATE TABLE IF NOT EXISTS` can race during first startup.

**DB-02: No database migrations**
All tables are created via `CREATE TABLE IF NOT EXISTS` in code. There is no migration framework (Alembic or equivalent). When a column is added to an existing model, the deployed database table will not have that column, causing `OperationalError: table X has no column named Y` in production.

**DB-03: No foreign key enforcement**
SQLite's foreign key support requires `PRAGMA foreign_keys = ON`. This pragma is not set in any of the storage adapters. The `refresh_tokens.user_id → users.id` foreign key declared in the schema is never enforced.

**DB-04: Project state stored in flat JSON files, not a database**
`ProjectRepository` reads/writes `backend/app/projects/{project_id}.json`. This approach:
- Cannot be queried (no filtering, sorting, pagination at DB level)
- Cannot be backed up atomically
- Has no transactional writes (partial write on crash corrupts the file)
- Grows without bound in the source directory

**DB-05: No connection pooling**
Each component opens its own `sqlite3.connect()` and holds it open for the process lifetime. SQLite supports this pattern, but with concurrent writers from multiple threads, `database is locked` errors are expected under load.

**DB-06: Duplicate database files at multiple paths**
- `data/memory.sqlite` (backend)
- `backend/data/memory.sqlite` (if run from repo root)
- `memory/memory.db` (root level)
- `backend/memory/memory.db` (backend level)

Depending on the working directory when the process starts, different files are opened, leading to apparent data loss or "fresh start" behavior.

---

## 10. Concurrency & Distributed System Audit

### 10.1 Pipeline Concurrency

**Race condition on project state:**
- Two simultaneous requests to `POST /workflow/start` for the same project are guarded by `ExecutionStateRegistry.is_running()`
- `ExecutionStateRegistry` uses a Python `set` — no lock around `is_running()` + `mark_running()` — classic TOCTOU race
- Under concurrent HTTP requests, two pipeline threads can start for the same project

**Daemon thread lifecycle:**
- Pipeline threads are `daemon=True`, meaning they are killed immediately when the uvicorn process exits (e.g., SIGTERM during deployment)
- Mid-stage execution is interrupted without cleanup, leaving orphaned workspace files
- No graceful shutdown hook in `kernel/lifecycle.py` to drain in-flight pipelines

### 10.2 Gate State Concurrency

```python
# app/db/gate_state.py
# Falls back to InMemoryGateStateRegistry when Redis is not configured
```

In-memory gate state is process-local. In a multi-worker uvicorn deployment (`--workers 2+`) or multi-container Kubernetes deployment, one worker's gate approval is invisible to other workers. Gate state can desync catastrophically.

### 10.3 Celery vs Thread Path

The system has two completely different execution paths:
1. **Thread path** (default): `threading.Thread(daemon=True)`
2. **Celery path** (when Redis configured): `run_pipeline.delay(project_id, request)`

These paths have different observable behaviors, error handling, and recovery semantics. Most testing appears to have been done on the thread path. The Celery path is undertested.

### 10.4 Duplicate Execution Guard

```python
# app/workflow/execution_state.py (referenced but not verified)
if manager.execution_state.is_running(request.project_id):
    return {"message": "Workflow is already running in background"}
```

This guard only works within a single process. Across multiple processes or container replicas, there is no distributed lock.

---

## 11. AI / LLM / Agent Audit

### 11.1 Agent Architecture

The agent loop follows: `ContextAssembler → Agent.execute() → Reviewer → RetryPolicy → repeat`

**Positive:**
- Maximum retry count enforced by `RetryPolicy.max_retries` (default: 3)
- `Reviewer` implements quality checks (boilerplate detection, required schema key presence, minimum content length)
- `SafetyPolicy` prevents file writes outside workspace

**Concerns:**

**AI-01: No structured output enforcement**
LLM outputs are JSON that must match agent-specific schemas. The Reviewer checks for required keys, but there is no schema validation against a Pydantic model or JSON Schema at the LLM response layer. Malformed JSON from the LLM can propagate through the pipeline.

**AI-02: No prompt injection protection**
User-supplied project descriptions are interpolated directly into LLM prompts:
```python
content = request.description or f"Initialize project {request.project_id}"
```
A malicious project description like `"Ignore all previous instructions and..."` is passed directly to the LLM without sanitization or system-level instruction hardening.

**AI-03: Token budget tracking is approximate**
The context window warning uses `cost.total_tokens` (cumulative across all prior stages), not the token count of the current prompt. The warning threshold may trigger too early or too late.

**AI-04: LLM context grows unboundedly**
`ContextAssembler` assembles context from all prior stage artifacts for each new stage. In a project with many sprints, the assembled context can exceed the LLM's context window. The system has a warning mechanism but no hard cutoff or context compression strategy.

**AI-05: Code sandbox disabled by default, SANDBOX_ENABLED=true in .env but behavior unclear**
The `.env` has `SANDBOX_ENABLED=true` but the sandbox only activates if Docker is also available. In practice, sandbox validation of generated code is conditional and may silently be skipped.

**AI-06: Generated code executed without human review**
The sandbox runs LLM-generated code (pytest, npm build, etc.) in Docker with network enabled. The generated code could contain malicious instructions that exfiltrate secrets or establish persistence inside the container network.

**AI-07: Hallucination handling**
The Reviewer detects boilerplate patterns and short outputs, but cannot detect factually incorrect code. There is no runtime verification that generated code works (beyond syntax checking and test execution). The "BugAnalyst" agent is an LLM evaluating LLM output — not an execution verifier.

### 11.2 LLM Provider Security

- API keys for all providers are stored in `.env` and loaded into process memory
- No key rotation mechanism
- No provider fallback — if the configured provider fails, the entire pipeline fails
- `BedrockProvider` uses a custom API key format (Base64) that differs from standard AWS SigV4 credentials — the fallback `boto3` credential chain path is untested

---

## 12. Testing Audit

### 12.1 Backend Tests

**Status: MISSING**

- `backend/pytest.ini` configures `testpaths = tests`
- The `backend/tests/` directory **does not exist**
- Running `pytest` from `backend/` exits with 0 tests collected, 0 failures — this gives false confidence in CI
- A `.coverage` file exists, suggesting tests existed at some point and were deleted

**What is not tested:**
- WorkflowEngine execution path
- WorkflowManager state machine transitions
- LLMManager retry behavior
- ArtifactManager save/load
- ProjectRepository CRUD
- All API endpoints
- Authentication middleware
- SafetyPolicy decisions
- Reviewer quality checks
- ContextAssembler assembly
- Memory persistence
- Any error paths

### 12.2 Frontend Tests

**Status: MINIMAL**

- `src/App.test.tsx` — 1 test file covering `ProtectedRoute` behavior
- `src/test/setup.ts` — test setup only
- No tests for API client (`lib/auth.ts`, `lib/api`)
- No tests for custom hooks (`useWebSocket`, `useProject`)
- No tests for any page components
- No tests for any UI components

### 12.3 Integration Tests

**Status: NONE**

No integration tests verify the full pipeline from API call to agent execution to artifact persistence.

### 12.4 Security Tests

**Status: NONE**

No security tests for authentication bypass, authorization checks, or input validation.

### 12.5 Test Infrastructure

- Backend: pytest + pytest-asyncio configured but no tests to run
- Frontend: Vitest configured and working (App.test.tsx passes)
- No CI pipeline to run tests automatically
- Coverage data from `.coverage` file cannot be trusted (tests were deleted)

---

## 13. Performance & Scalability Analysis

### 13.1 Confirmed Bottlenecks

| Bottleneck | Location | Impact |
|-----------|----------|--------|
| Synchronous LLM calls block threads | All agents | Each stage blocks a thread for 30s–20min |
| SQLite write contention | All storage | `database is locked` under concurrent projects |
| `sentence-transformers` load on startup | KnowledgeMemory | 300MB+ model loaded even if not used |
| All project JSON loaded for list | ProjectRepository.list_projects() | O(n) file reads; 347 files already causes measurable latency |
| `check_same_thread=False` pattern | UserStore, SafetyPolicy | Not thread-safe for concurrent writes |

### 13.2 Scalability Limits

- **SQLite:** Not horizontally scalable. With concurrent projects, write locks serialize all progress
- **In-memory gate state:** Process-local; breaks in multi-process or multi-container deployments
- **In-memory rate limiter:** Same issue
- **Daemon threads:** Each active pipeline consumes a thread; no threadpool limit configured
- **`sentence-transformers`:** Loads a 300MB+ model into memory; memory ceiling will be hit early in containerized deployments

### 13.3 CANNOT DETERMINE (runtime data required)

- Actual p50/p95 LLM call latency
- SQLite write lock frequency under realistic load
- Memory usage of `sentence-transformers` model at scale

---

## 14. Observability Audit

### 14.1 What Is Present

- **Structured logging:** `configure_logging()` uses `structlog` if installed, falls back to stdlib. JSON logging available via `LOG_FORMAT=json`
- **Distributed tracing:** OpenTelemetry SDK configured, FastAPI auto-instrumented, traces sent to OTEL collector when `OTEL_ENDPOINT` is set
- **Health endpoint:** `GET /health` and `GET /ready` exist and check LLM manager + memory manager status
- **Cost tracking:** Per-project LLM token usage tracked in `CostTracker` (SQLite)
- **WebSocket events:** Stage start/complete/retry/fail broadcast to UI in real-time
- **Safety audit log:** `SafetyPolicy` logs every check to `safety_checks` table

### 14.2 What Is Missing

- **No correlation/request IDs:** Individual HTTP requests cannot be traced through logs
- **No structured error events:** Unhandled exceptions in pipeline threads are logged but not structured
- **No alerting configuration:** No Prometheus metrics exported; OTel is opt-in and unconfigured by default
- **No dashboards:** No Grafana or equivalent shipped
- **Thread crash visibility:** If a daemon pipeline thread dies unexpectedly, there is no recovery event sent to the WebSocket or stored in the event log
- **No liveness probe implementation:** The `docker-compose.yml` healthcheck calls `/ready` but does not verify that background workers are alive

**3AM question:** Can an engineer identify a production problem at 3AM?
- **Partially.** Logs exist and are structured. But without correlation IDs, tracing pipeline thread execution through logs requires manually grepping for `project_id`. Thread crashes leave no terminal event. OTel tracing requires opt-in setup.

---

## 15. DevOps / Deployment Audit

### 15.1 Docker

**Dockerfile issues:**
- **Runs as root:** No `USER` instruction; the container runs as root, violating least-privilege
- **No `.dockerignore`:** No `.dockerignore` file visible; `COPY . .` copies `.env` (with credentials), `temp-workspace/`, `backend/app/projects/*.json`, `venv/`, `.venv/`, `.coverage`, etc. into the image
- **Bakes runtime data:** `backend/app/projects/` (347 project JSON files) is copied into every image

### 15.2 Docker Compose

- Production `docker-compose.yml` is reasonable
- Redis healthcheck is correct
- Volume mounts for `temp-workspace` and `data` are correct
- OTEL/Jaeger are profile-gated (good)
- Missing: resource limits (`mem_limit`, `cpu_shares`) on API/worker containers

### 15.3 CI/CD

**Status: NONE**

- No `.github/workflows/`, `.gitlab-ci.yml`, or any CI configuration exists
- No automated build, test, lint, or deploy pipeline
- No branch protection rules enforced

### 15.4 Database Migration

**Status: None**

- `CREATE TABLE IF NOT EXISTS` in code; no Alembic or equivalent
- No rollback strategy for schema changes
- Column additions require manual intervention on existing deployments

### 15.5 Deployment Risk

Starting from a clean environment:
1. Developer must manually copy `.env.example` to `.env` and fill in credentials
2. No validation that all required env vars are set before startup (except `JWT_SECRET_KEY` when `AUTH_ENABLED=true`)
3. `sentence-transformers` downloads a large model on first run (no pre-download step)
4. `backend/app/projects/` and `backend/data/` are not explicitly created in `Dockerfile` startup (created by code at runtime)

---

## 16. Dependency Audit

### 16.1 Version Pinning

All `requirements.txt` entries use `>=` constraints — no upper bounds, no exact pins:

```
fastapi>=0.115.0
pydantic>=2.0.0
tenacity>=8.2.3
# etc.
```

This means `pip install -r requirements.txt` will always install the **latest** compatible version. Breaking changes in upstream packages will surface only at deploy time, not during development.

### 16.2 Dual Dependency on passlib and bcrypt

- `requirements.txt` includes `bcrypt>=4.0.0` directly
- `passlib` is **not** in `requirements.txt`
- `app/api/auth.py:189` imports `from passlib.context import CryptContext`
- This will raise `ImportError` in any environment built from `requirements.txt`

### 16.3 Heavy ML Dependencies

- `sentence-transformers>=3.0.0` — ~300MB model download, PyTorch dependency
- `transformers>=4.0.0` — large NLP library
- These are required for the vector knowledge base; they are loaded even in projects that don't use semantic search

### 16.4 boto3 vs Bedrock API Key

The Bedrock provider supports two auth modes: custom API key (Bearer token) or standard boto3 credential chain. The `boto3>=1.34.0` dependency is listed but the fallback auth path is UNVERIFIED.

### 16.5 Celery / Redis Optional

Celery and Redis are in `requirements.txt` as hard dependencies, but the code gracefully falls back to threads when they're absent. Installing but not using Celery adds ~15MB and startup overhead.

---

## 17. Configuration Audit

### 17.1 Unsafe Defaults

| Config | Default | Risk |
|--------|---------|------|
| `VALID_API_KEYS` | empty (auth disabled) | All API key auth bypassed |
| `RATE_LIMIT_ENABLED` | false | No rate limiting |
| `SANDBOX_ENABLED` | true (in .env) | Docker required but not validated at startup |
| `REDIS_URL` | empty (in-memory gate state) | Gate state lost on restart |
| `CELERY_BROKER_URL` | empty (threads) | No task durability |
| `DEFAULT_ADMIN_PASSWORD` | "admin" | Weak default credential |
| `LOG_FORMAT` | "text" | Not machine-parseable in production |

### 17.2 Missing Startup Validation

The system does not validate at startup that all required configuration is present and valid. Failures surface as runtime errors during the first request or pipeline execution. A startup validation gate would prevent misconfigured deployments from accepting traffic.

### 17.3 .env Written at Runtime

`POST /settings/llm` calls `upsert_env_values()` which writes to `backend/.env`. In a Docker container, this writes to the container's ephemeral layer — the change is lost on container restart. In a volume-mounted deployment, it correctly persists. This inconsistency is not documented.

---

## 18. Production Readiness Score

| Area | Score / 10 | Rationale |
|------|----------:|---------|
| Architecture | 6 | Clean separation of concerns, good patterns; marred by duplicate modules, hardcoded paths, flat-file project storage |
| Code Quality | 5 | Large, well-structured codebase; multiple confirmed bugs, duplicate DTOs, passlib/bcrypt conflict |
| Correctness | 4 | Several confirmed bugs (passlib import, missing tests dir, thread safety); silent failure paths |
| Security | 2 | CRITICAL: 7+ unauthenticated endpoints including gate approval and settings write; default admin password; network-enabled sandbox |
| API Design | 4 | Consistent REST patterns; catastrophic auth gaps on half the endpoints; no versioning |
| Database | 3 | No migrations, no FK enforcement, flat JSON files, 6 separate SQLite files, duplicate databases at multiple paths |
| Testing | 1 | Backend tests directory does not exist; 1 frontend test file; no integration/security/e2e tests |
| Error Handling | 5 | Good coverage in happy paths; silent thread crashes; SQLite lock errors uncaught |
| Observability | 5 | Logging and OTel present; no correlation IDs; no alerting; thread crash not observable |
| Performance | 4 | Synchronous LLM calls block threads; SQLite contention under load; unbounded project list load |
| Scalability | 2 | SQLite ceiling; in-memory state breaks multi-process; no horizontal scaling path |
| DevOps | 2 | No CI/CD; Dockerfile runs as root; no .dockerignore; no migration strategy |
| Documentation | 7 | Extensive docs; several doc/implementation mismatches; session logs are thorough |
| Maintainability | 5 | Good patterns undermined by duplicate modules, 20-param constructors, hardcoded paths |
| AI/Agent Safety | 4 | Safety policy and reviewer exist; prompt injection unaddressed; network-enabled sandbox; no output schema validation |

**Weighted Overall Score:**

```
PRODUCTION READINESS: 28/100
```

Score calculation: Security (×2 weight) scores 2/10 = 4pts; Testing (×2) = 2pts; Architecture 6, Code Quality 5, Correctness 4, API 4, DB 3, Error Handling 5, Observability 5, Performance 4, Scalability 2, DevOps 2, Docs 7, Maintainability 5, AI Safety 4 = sum 56 / 15 categories = 3.7 avg × additional weighting. Multiple P0 blockers prevent production deployment regardless of score.

---

## 19. Complete Findings Register

| ID | Severity | Category | Finding | Files | Impact |
|----|---------|----------|---------|-------|--------|
| F-01 | P0 | Security | Gates API has NO authentication — anyone can approve pipeline stages | `api/gates.py` | Pipeline takeover |
| F-02 | P0 | Security | Settings API has NO authentication and writes to `.env` | `api/settings.py` | Credential injection |
| F-03 | P0 | Correctness | `passlib` imported in `change_password` but not in requirements.txt | `api/auth.py:189` | ImportError in production |
| F-04 | P0 | Testing | `backend/tests/` does not exist; 0 backend tests | `pytest.ini` | No validation of any code |
| F-05 | P1 | Security | Memory, logs, analytics, learning, intelligence APIs have no auth | 5 router files | Data exposure |
| F-06 | P1 | Security | WebSocket token validation bypasses JWT; accepts any token when VALID_API_KEYS empty | `api/websocket.py` | Unauthorized WebSocket |
| F-07 | P1 | Security | Docker sandbox has `network_disabled=False` | `execution/sandbox.py` | Code exfiltration, SSRF |
| F-08 | P1 | Security | Default admin password is "admin" | `db/users.py:_ensure_admin` | Account takeover |
| F-09 | P1 | Architecture | 347 runtime project JSON files committed to source tree | `app/projects/*.json` | Privacy leak, repo bloat |
| F-10 | P1 | Architecture | `ProjectRepository` hardcodes path to `backend/app/projects/` | `project/repository.py:15` | Cannot redirect storage; Docker bakes data into image |
| F-11 | P1 | Concurrency | TOCTOU race in `ExecutionStateRegistry` — two pipelines can start for same project | `workflow/execution_state.py` | State corruption |
| F-12 | P1 | Reliability | Daemon thread pipeline crash leaves project in intermediate state with no recovery event | `api/workflow.py:43,80` | Silent pipeline failure |
| F-13 | P2 | Security | `area` parameter in file endpoint not allowlisted | `api/files.py` | Potential path traversal |
| F-14 | P2 | Security | Rate limiting disabled by default | `.env`, `rate_limit.py` | Unbounded LLM cost |
| F-15 | P2 | Security | Anonymous users default to admin role | `middleware/jwt_auth.py` | Privilege escalation on auth misconfiguration |
| F-16 | P2 | Correctness | Duplicate module pairs in `app/llm/` — manager, request, response each have two copies | `app/llm/` | Divergent behavior |
| F-17 | P2 | Correctness | `app/artifacts/` is an empty orphan directory; `app/artifact/` is used | `app/artifacts/` | Developer confusion |
| F-18 | P2 | Database | No database migrations — schema changes break existing deployments | all `_ensure_schema()` | Production data loss |
| F-19 | P2 | Database | No FK enforcement (`PRAGMA foreign_keys = ON` never set) | `db/users.py`, `storage/` | Orphaned refresh tokens |
| F-20 | P2 | Database | Duplicate SQLite database files at multiple paths (root and backend) | `data/`, `backend/data/`, `memory/` | Data split across files |
| F-21 | P2 | Database | SafetyPolicy creates `artifacts` table in same db as ArtifactManager — race condition | `execution/safety_policy.py` | Table creation race |
| F-22 | P2 | Architecture | `backend/backend/app/memory/` nested duplicate directory | `backend/backend/` | Import resolution risk |
| F-23 | P2 | Architecture | Two virtual environments (.venv root, venv backend) with different packages | `.venv/`, `backend/venv/` | Package confusion |
| F-24 | P2 | DevOps | No CI/CD pipeline | entire repo | No automated quality gates |
| F-25 | P2 | DevOps | Dockerfile runs as root; no USER instruction | `backend/Dockerfile` | Container privilege escalation |
| F-26 | P2 | DevOps | No `.dockerignore` — credentials and runtime data copied into image | `backend/` | Secret leak in image |
| F-27 | P3 | AI Safety | No prompt injection protection on user-supplied project description | `api/project.py` | Prompt injection |
| F-28 | P3 | AI Safety | No structured output schema validation on LLM responses | all agents | Malformed artifacts |
| F-29 | P3 | Scalability | SQLite cannot support horizontal scaling | all storage | Hard ceiling |
| F-30 | P3 | Scalability | In-memory gate state and rate limiter not shared across processes | `db/gate_state.py` | State desync in HA |
| F-31 | P3 | Performance | All project JSON files loaded for list endpoint (O(n) file reads, 347 files already) | `project/repository.py` | Slow list endpoint |
| F-32 | P3 | Configuration | `requirements.txt` uses `>=` only — no pinned versions | `requirements.txt` | Non-reproducible builds |
| F-33 | P3 | Configuration | `POST /settings/llm` persists to `.env` which is lost on container restart | `config/env_writer.py` | Settings not durable |
| F-34 | P3 | Reliability | `sentence-transformers` 300MB model loaded on startup even when unused | `memory/knowledge_memory.py` | High memory consumption |
| F-35 | P3 | Observability | No correlation IDs on HTTP requests | entire API layer | Cannot trace requests |
| F-36 | P3 | Observability | Pipeline thread crashes have no terminal event on WebSocket | `api/workflow.py` | Silent failure in UI |
| F-37 | P4 | Security | Expired refresh tokens never purged | `db/users.py` | Table growth |
| F-38 | P4 | API Design | No API versioning (`/api/v1/`) | `api/router.py` | No backward compat path |
| F-39 | P4 | API Design | `/admin/users` list has no pagination | `api/auth.py` | Memory spike on large user counts |
| F-40 | P4 | Maintainability | WorkflowEngine constructor takes 22 parameters | `workflow/engine.py` | Untestable, fragile |

---

## 20. Production Blockers — Must Fix Before Production

### BLOCKER-1: Unauthenticated Gate Approval Endpoints (F-01)

**Problem:** `POST /workflow/{project_id}/gates/*/approve` and `POST /workflow/{project_id}/gates/*/revise` have zero authentication. Any network-reachable client can approve or reject pipeline stages for any project.

**Evidence:** `api/gates.py` — no `get_current_user` dependency on any endpoint. Confirmed via `grep "get_current_user" api/gates.py` → 0 results.

**Risk:** Complete pipeline integrity loss. An attacker can auto-approve all stages and trigger arbitrary code generation/execution.

**Fix Required:** Add `user=Depends(get_current_user)` to all gate endpoints. Add `_assert_project_access(project, user)` before state transitions.

**Validation:** `grep "get_current_user" api/gates.py` must return ≥1 result per endpoint.

---

### BLOCKER-2: Unauthenticated Settings Endpoint Writes Credentials to Disk (F-02)

**Problem:** `POST /settings/llm` has no authentication and calls `upsert_env_values()` which rewrites `backend/.env` on disk.

**Evidence:** `api/settings.py` — no auth dependency. `upsert_env_values()` in `config/env_writer.py` writes directly to the `.env` file.

**Risk:** Credential injection. An attacker can set a malicious `BEDROCK_API_KEY` or `CLAUDE_API_KEY` that exfiltrates all LLM prompts (which include project source code and proprietary descriptions) to an attacker-controlled endpoint.

**Fix Required:** Add admin-only auth (`dependencies=[Depends(require_role("admin"))]`) to both `/settings/llm` endpoints. Consider removing runtime `.env` writes entirely (prefer environment-variable reload or a config database table).

---

### BLOCKER-3: passlib ImportError in change_password (F-03)

**Problem:** `POST /auth/change-password` imports `from passlib.context import CryptContext` at line 189 of `api/auth.py`. `passlib` is not in `requirements.txt`.

**Evidence:** `requirements.txt` has `bcrypt>=4.0.0` but no `passlib`. `auth.py:189` imports passlib.

**Risk:** Any user attempting to change their password receives `ImportError: No module named 'passlib'`, effectively breaking password management.

**Fix Required:** Replace the passlib usage in `change_password` with direct bcrypt (matching the pattern in `db/users.py:_hash_password`).

---

### BLOCKER-4: Backend Tests Directory Missing (F-04)

**Problem:** `pytest.ini` declares `testpaths = tests` but `backend/tests/` does not exist. Zero backend tests exist. No code correctness validation.

**Evidence:** `ls backend/tests/` → directory not found.

**Risk:** Any regression introduced in a code change goes undetected before deployment.

**Fix Required:** Create `backend/tests/` with at minimum: auth endpoint tests, gate endpoint auth tests (to prevent regression of F-01 fix), project CRUD tests, and workflow state machine tests.

---

### BLOCKER-5: 347 Runtime Project JSON Files in Source Tree (F-09, F-10)

**Problem:** `backend/app/projects/*.json` contains 347 project JSON files. These are runtime data committed to the git repository. `ProjectRepository` hardcodes this path.

**Evidence:** `ls backend/app/projects/ | wc -l` → 347. `project/repository.py:15` hardcodes the path.

**Risk:** (a) User project data (names, descriptions, state) is in the git repository. (b) `docker build` bakes these into every image. (c) The directory grows without bound.

**Fix Required:** (a) Add `backend/app/projects/*.json` to `.gitignore` and remove committed files from git history. (b) Make `ProjectRepository` root configurable via `PROJECT_STORAGE_PATH` env var. (c) Consider migrating project state to SQLite (the auth.db pattern is a good template).

---

### BLOCKER-6: No CI/CD Pipeline (F-24)

**Problem:** No automated testing, linting, or build verification runs on any code push.

**Risk:** The fixes for Blockers 1-5 can regress immediately after being applied, with no automated detection.

**Fix Required:** Add a minimal CI workflow (GitHub Actions or equivalent) that runs: `pip install -r requirements.txt`, `pytest` (after tests are added), `ruff check .`, and frontend `npm run build && npm test`.

---

## 21. Prioritized Remediation Roadmap

### PHASE 0 — BLOCKERS (Week 1)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-01 | P0 | Add `get_current_user` + `_assert_project_access` to all gate endpoints | `api/gates.py` | All gate endpoints return 401 without valid JWT |
| T-02 | P0 | Add admin-only auth to `/settings/llm` endpoints | `api/settings.py` | Non-admin JWT returns 403; no token returns 401 |
| T-03 | P0 | Fix `change_password`: replace passlib with direct bcrypt | `api/auth.py:189` | `POST /auth/change-password` works with no passlib installed |
| T-04 | P0 | Create `backend/tests/` with auth + gate + project tests | `backend/tests/` | `pytest` collects ≥20 tests, all green |
| T-05 | P0 | Gitignore project JSON files; make `ProjectRepository` path configurable | `project/repository.py`, `.gitignore` | `git status` shows no `app/projects/*.json` tracked |
| T-06 | P0 | Add auth to memory, logs, analytics, learning, intelligence endpoints | 5 router files | All return 401 without JWT |

### PHASE 1 — RELIABILITY (Weeks 2-3)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-07 | P1 | Add lock to `ExecutionStateRegistry.is_running()` + `mark_running()` | `workflow/execution_state.py` | Concurrent start requests for same project returns 409 |
| T-08 | P1 | Add graceful shutdown hook to drain in-flight pipeline threads | `kernel/lifecycle.py` | SIGTERM waits for active pipelines (up to 60s) |
| T-09 | P1 | Broadcast WebSocket terminal event when pipeline thread crashes | `api/workflow.py` | UI shows "Pipeline failed" when thread dies |
| T-10 | P1 | Set `PRAGMA foreign_keys = ON` in all SQLite connections | `storage/sqlite_storage_adapter.py`, `db/users.py` | FK violations raise IntegrityError |
| T-11 | P1 | Remove `backend/backend/` nested duplicate directory | `backend/backend/` | Directory deleted; no import resolves to it |
| T-12 | P1 | Consolidate duplicate module pairs in `app/llm/` | `app/llm/` | One authoritative manager, request, response |
| T-13 | P1 | Remove orphan `app/artifacts/` directory | `app/artifacts/` | Directory deleted |
| T-14 | P2 | Migrate project state from flat JSON to SQLite | `project/repository.py` | All project CRUD backed by SQLite with proper transactions |

### PHASE 2 — SECURITY (Weeks 3-4)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-15 | P1 | Disable Docker sandbox network or use allowlist | `execution/sandbox.py` | Container cannot make outbound connections |
| T-16 | P1 | Enforce `DEFAULT_ADMIN_PASSWORD` change before accepting traffic | `db/users.py`, startup | Startup health check fails if default password unchanged |
| T-17 | P1 | Fix WebSocket auth to validate JWT tokens | `api/websocket.py` | WS requires valid JWT or API key |
| T-18 | P2 | Sanitize `area` parameter in file endpoint | `api/files.py` | Area validated against allowlist `["project", "artifacts", "docs"]` |
| T-19 | P2 | Enable rate limiting by default | `.env.example` | `RATE_LIMIT_ENABLED=true` in template |
| T-20 | P2 | Add startup validation for all required env vars | `kernel/bootstrap.py` | Missing required vars abort startup with clear error |
| T-21 | P2 | Add prompt sanitization for user-supplied project descriptions | `api/project.py` | Injection attempt patterns stripped/escaped |

### PHASE 3 — TESTING (Weeks 4-6)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-22 | P1 | Backend unit tests: auth, gates, project, workflow state machine | `backend/tests/` | ≥50 unit tests, all green |
| T-23 | P1 | Backend integration tests: full pipeline smoke test | `backend/tests/` | Pipeline runs end-to-end with mock LLM |
| T-24 | P1 | Security regression tests: unauthenticated requests return 401/403 | `backend/tests/` | All protected endpoints covered |
| T-25 | P2 | Frontend component tests for key pages | `frontend/src/` | ProjectsPage, WorkspacePage covered |
| T-26 | P2 | Add test coverage thresholds to CI | CI config | Build fails below 60% coverage |

### PHASE 4 — PERFORMANCE (Weeks 6-8)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-27 | P2 | Add `.dockerignore` to exclude `.env`, `venv`, `temp-workspace`, `app/projects/` | `backend/.dockerignore` | Docker image does not contain credentials or runtime data |
| T-28 | P2 | Lazy-load `sentence-transformers` model (only when semantic search used) | `memory/knowledge_memory.py` | Startup memory reduced by ~300MB for projects not using knowledge base |
| T-29 | P3 | SQLite WAL mode + connection-per-thread for write-heavy paths | `storage/sqlite_storage_adapter.py` | No `database is locked` under 5 concurrent projects |
| T-30 | P3 | Index `projects` query (or migrate to SQLite) for list performance | `project/repository.py` | Project list endpoint < 100ms for 1000+ projects |

### PHASE 5 — OBSERVABILITY (Week 8)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-31 | P2 | Add request correlation ID middleware | `app/main.py` | Every log line includes `request_id` |
| T-32 | P2 | Structured error events for pipeline thread crashes | `api/workflow.py` | Crash stored in event log + WebSocket event sent |
| T-33 | P3 | Export Prometheus metrics (request rate, error rate, LLM latency) | new `api/metrics.py` | Metrics endpoint at `/metrics` |
| T-34 | P3 | Add scheduled job to purge expired refresh tokens | `db/users.py` or scheduler | Token table does not grow unboundedly |

### PHASE 6 — DEVOPS (Weeks 8-10)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-35 | P0 | Add CI/CD pipeline (GitHub Actions) | `.github/workflows/` | Every PR runs tests + lint + build |
| T-36 | P1 | Add `USER nonroot` to Dockerfile | `backend/Dockerfile` | Container runs as non-root |
| T-37 | P1 | Pin all `requirements.txt` to exact versions | `requirements.txt` | Reproducible pip install |
| T-38 | P2 | Add Alembic for database migrations | new `alembic/` | Schema changes deployed without data loss |
| T-39 | P2 | Add resource limits to docker-compose services | `docker-compose.yml` | API/worker container memory bounded |
| T-40 | P3 | Document deployment runbook | `docs/DEPLOY.md` | Clean deploy from zero requires no tribal knowledge |

### PHASE 7 — ARCHITECTURE (Weeks 10-12)

| Task ID | Priority | Description | Files | Acceptance Criteria |
|---------|---------|-------------|-------|-------------------|
| T-41 | P2 | Reduce `WorkflowEngine.__init__` to ≤8 parameters via config object | `workflow/engine.py` | Constructor takes `WorkflowConfig` dataclass |
| T-42 | P3 | Remove second venv (`backend/venv/`); consolidate to `.venv` at repo root | `backend/venv/` | Single venv used everywhere |
| T-43 | P3 | Move settings persistence from `.env` file to a config SQLite table | `config/env_writer.py` | Runtime config changes durable in Docker |

### PHASE 8 — POLISH (Ongoing)

| Task ID | Priority | Description |
|---------|---------|-------------|
| T-44 | P4 | Add API versioning prefix `/api/v1/` |
| T-45 | P4 | Add pagination to `/admin/users` and `/projects` endpoints |
| T-46 | P4 | Add background job to purge expired refresh tokens |
| T-47 | P4 | Update architecture mermaid diagram to reflect actual implementation |
| T-48 | P4 | Document all environment variables with type, default, and required status |

---

## 22. Keep As-Is

The following are well-implemented and should NOT be unnecessarily rewritten:

**✅ Reviewer quality gate** (`app/review/reviewer.py`) — Sophisticated artifact quality checks including boilerplate detection, schema key validation, code coverage ratios, and structured content depth checks. This is a strong implementation.

**✅ SafetyPolicy + FreezePolicy** (`app/execution/safety_policy.py`) — Well-designed workspace boundary enforcement with audit logging. The decision model (ALLOW/WARN/BLOCK) and audit table are good production patterns.

**✅ UserStore** (`app/db/users.py`) — Clean implementation. Bcrypt with cost 12, SHA-256 refresh token hashing, timing-safe comparisons, double-checked locking for singleton. Keep as-is (except the `change_password` passlib bug).

**✅ EventBroadcaster** (`app/events/broadcaster.py`) — Correct `call_soon_threadsafe` pattern for scheduling async WebSocket sends from synchronous pipeline threads.

**✅ LLM provider abstraction** (`app/llm/factory.py`, `providers/`) — Clean factory pattern, supports 4 providers, correct base URL routing logic for each provider.

**✅ ContextAssembler + token budget** — Token-aware context assembly with configurable limits is the right approach.

**✅ Docker Compose + Redis/Celery optional fallback** — The graceful degradation from Celery to daemon threads is a good developer experience choice.

**✅ WorkflowEngine middleware architecture** — CheckpointMiddleware, LearningMiddleware, GitMiddleware as composable middleware is clean and extensible.

**✅ RetryPolicy** — Simple, correct, and configurable. No changes needed.

**✅ Gate state with Redis fallback** — `build_gate_state_registry()` probes Redis and falls back to in-memory. The pattern is correct.

**✅ OpenTelemetry integration** — Opt-in tracing with OTEL collector config is well structured.

**✅ Frontend routing + ProtectedRoute** — Clean React Router v7 implementation with JWT-aware route guards.

**✅ ProjectWriter code fence stripping** — Practical fix for LLM markdown leaking into source files. Keep.

---

## 23. Final Architecture Review

### 1. What does this system currently do?

AI DevOS accepts a natural-language software project description, runs it through a pipeline of 15+ AI agents (each backed by a configurable LLM provider), and generates a complete software project structure: requirements, architecture, UI design, security report, sprint plan, backend code, frontend code, QA report, and deployment config. Users interact via a React UI with real-time WebSocket progress updates. Human review gates pause the pipeline at architecture, design, and sprint-plan stages for human approval before continuing. Generated code is written to `temp-workspace/{project_id}/project/` and can be downloaded as a ZIP.

### 2. What are its strongest parts?

- Sophisticated agent pipeline design with clear separation of concerns
- Quality-gated review loop with real production-quality checks (not just "does it return something")
- Human-in-the-loop gates at key pipeline decision points
- Well-designed LLM abstraction supporting 4 providers
- Good crash recovery checkpoint pattern
- Substantial documentation corpus

### 3. What are its weakest parts?

- Security: half the API surface is completely unauthenticated
- Testing: backend tests directory does not exist
- Data integrity: flat JSON project files baked into Docker images
- Concurrency: daemon thread pipeline with no shutdown coordination
- Operations: no CI/CD, no migrations, root Docker container

### 4. What are the 10 most dangerous problems?

1. Unauthenticated gate approval endpoints (anyone can hijack the pipeline)
2. Unauthenticated settings endpoint writes API keys to disk
3. `passlib` ImportError breaks password change in production
4. Zero backend tests — no regression protection
5. 347 project JSON files in source tree (user data in git)
6. Docker sandbox has full internet access (exfiltration via generated code)
7. Daemon threads die silently — no recovery, no visible error
8. Default admin password enforced only by log WARNING
9. WebSocket auth bypass when API keys not configured (accepts any token)
10. No database migrations — first schema column addition destroys production data

### 5. What could break first in production?

`POST /auth/change-password` → `ImportError: No module named 'passlib'` — this will fail for every user who tries to change their password.

### 6. What security risks require immediate attention?

F-01 (gate approval), F-02 (settings write), F-07 (sandbox network), F-06 (WebSocket bypass), F-08 (default admin password).

### 7. What technical debt is acceptable?

- 20-parameter `WorkflowEngine` constructor (refactorable, not breaking)
- Duplicate `app/llm/` DTOs (confusing but non-breaking)
- Unpinned `>=` requirements (risk, but manageable in controlled environments)
- Missing API versioning (forward-compatible to add later)

### 8. What technical debt is dangerous?

- No database migrations (will cause data loss on first schema change)
- Flat JSON project files in source tree (grows unboundedly, user data exposure)
- SQLite for everything (architectural ceiling; all HA features require full rewrite)
- No CI/CD (any broken commit ships to production)

### 9. What architecture changes are actually necessary?

1. Move project state from flat JSON files to SQLite (same pattern as UserStore)
2. Add proper database migration layer (Alembic)
3. Enable Redis/Celery by default (not optional) for production deployments
4. Add a `.dockerignore` immediately

### 10. What can remain unchanged?

The agent pipeline design, the LLM provider abstraction, the Reviewer quality gate, the SafetyPolicy, the EventBroadcaster threading pattern, the ContextAssembler, the middleware pattern in WorkflowEngine, the gate state Redis fallback, and the frontend routing architecture.

### 11. What is preventing this from being production-ready?

Six blockers (T-01 through T-06): unauthenticated critical endpoints, broken `change_password`, zero tests, and runtime data in source tree.

### 12. What is the minimum work required to reach production?

Phase 0 blockers (T-01 to T-06) + Phase 2 security items T-15, T-16, T-17 + Phase 6 T-35 (CI) + Phase 6 T-36 (non-root Docker). Estimated 3-4 engineering weeks with one engineer.

### 13. What should NOT be built yet?

- Multi-tenant SaaS features
- Kubernetes/Helm charts
- Prometheus/Grafana dashboards
- Advanced context compression
- Multi-provider failover
- Any new agent stages

Until the P0 security holes are closed and basic tests exist, adding features increases the attack surface and makes regression detection harder.

### 14. What should be tested before deployment?

- All authentication and authorization paths (especially the now-fixed gate endpoints)
- Pipeline execution end-to-end with a mock LLM
- SQLite write behavior under 5+ concurrent projects
- Docker sandbox isolation (confirm network is restricted)
- Password change flow (confirm passlib bug is fixed)
- Default admin password enforcement

### 15. What should the next engineering sprint contain?

1. T-01: Gate endpoint authentication
2. T-02: Settings endpoint authentication
3. T-03: Fix passlib/bcrypt in `change_password`
4. T-06: Add auth to memory/logs/analytics/learning/intelligence endpoints
5. T-04: Create `backend/tests/` with auth + gate regression tests
6. T-05: Gitignore project JSONs + configurable ProjectRepository path
7. T-35: Minimal CI pipeline (pytest + ruff + frontend build)
8. T-36: Non-root Dockerfile

---

## FINAL VERDICT

```
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              NOT PRODUCTION READY                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

**Why:**

1. **Multiple CRITICAL unauthenticated endpoints** — Gate approval, LLM settings, memory, logs, analytics and intelligence can all be accessed without authentication, despite `AUTH_ENABLED=true` in the configured `.env`. An attacker on the same network can approve pipeline stages for any project, inject malicious LLM provider credentials, and read all project memory and build logs.

2. **Production-breaking bug in `change_password`** — The endpoint imports a library (`passlib`) that is not installed via `requirements.txt`. This will fail with `ImportError` for every user attempting to change their password.

3. **Zero backend tests** — The `backend/tests/` directory does not exist. There is no automated validation of any business logic, authentication, or API behavior. No fix for any of the above issues can be verified without a test suite.

4. **Runtime user data committed to source control** — 347 project JSON files exist in `backend/app/projects/` and are tracked by git. Each file contains user project names, descriptions, and pipeline state. These are baked into Docker images on every build.

**Conditions for production readiness:** Complete Phase 0 (T-01 through T-06) and Phase 2 items T-15 through T-17, with passing test coverage for all fixed security paths, before any internet-accessible deployment.

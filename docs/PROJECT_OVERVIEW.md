# Project Overview — AI DevOS

**Last Updated**: 2026-08-07
**Status**: Production-quality multi-agent pipeline with auth, mobile support, and sprint loop
**System Version**: 2.0

---

## What This Project Does

AI DevOS is a **multi-agent software engineering pipeline** that transforms natural-language project
descriptions into real, downloadable, runnable source code.

Describe an application in plain English → specialized AI agents (each backed by LLM + schema
validation + automated reviewer) → download real source files → run the generated project.

Unlike asking an LLM to write an app in one shot, AI DevOS:
- **Stages the work** across 19+ specialized agents with clear responsibility separation
- **Reviews each stage** with a three-tier gate (AUTO_FIX/ASK_HUMAN/FLAG) before the next stage runs
- **Generates real files** — Backend/Frontend code written to disk, not JSON artifacts
- **Learns from experience** via trajectory recording, knowledge embedding, and lesson storage
- **Resumes on crash** — ProjectState persisted on every transition; resumes from last saved state
- **Manages requirement changes** — Impact analysis identifies affected stages; only re-runs what changed
- **Supports mobile** — `mobile_app` project type dispatches to React Native / Expo pipeline
- **Enforces auth + ownership** — JWT auth with per-user project isolation

---

## System Architecture

### High-Level Topology

```
Frontend (Vite + React 19 + TypeScript, :5173)
  | HTTP via Vite proxy to localhost:8000 — no CORS config needed
  v
Backend (FastAPI, :8000)
  +- DI Container (kernel/container.py)
  |    ~40 singletons wired in Container.build()
  +- PipelineSupervisor (workflow/pipeline_supervisor.py)
  |    3-phase orchestrator: Discovery → Sprint Loop → Release
  +- WorkflowManager (workflow/manager.py)
  |    24-state machine; _run_sprint() per sprint
  +- WorkflowEngine (workflow/engine.py)
  |    execute → review → retry loop
  |    Injects: predecessor message, design context, lessons, patterns, intelligence context
  +- AgentFactory (agents/factory.py)
  |    Creates agents per stage; 17+ registered
  +- LLMManager (llm/manager.py)
  |    OllamaProvider (default) or BedrockProvider; runtime-switchable
  +- Auth Layer
  |    JWT middleware + RBAC; per-user project isolation via owner_id
  +- Memory System
  |    MemoryManager (SQLite), KnowledgeMemory (HNSW vectors),
  |    LearningLoop (trajectories), LessonStore, CheckpointManager, CostTracker
  +- Intelligence Layer
  |    FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator, SprintMonitor
  +- Events
       EventBroadcaster → WebSocket /ws/{project_id}
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend runtime | Python 3.10+, FastAPI (synchronous pipeline path) |
| Frontend | Vite 8, React 19, TypeScript 6, Tailwind CSS v4 |
| LLM (default) | Ollama local server, model: qwen2.5-coder:7b |
| LLM (alternate) | AWS Bedrock Runtime Converse API (Claude 3.5 Sonnet) |
| Auth | JWT (python-jose), bcrypt passwords, SQLite refresh tokens |
| Storage | SQLite (artifacts, memory, trajectories, lessons, file index, costs, users) |
| Vector search | HNSW (hnswlib) for knowledge embedding |
| Package manager | pip (backend), npm/vite (frontend) |

---

## The Pipeline: 3 Phases, 19+ Stages

### Phase 1 — Discovery (runs once)
```
DomainResearch → Clarification [Q&A gate]
  → StrategicReview → ProductOwner → Architect [review gate]
  → Designer [review gate] → Security → SprintPlanner
```

### Phase 2 — Sprint Loop (repeats per sprint)
```
ScrumMaster → FileStructurePlanner → BackendDeveloper → FrontendDeveloper
  → SprintDeploy → SprintReview
```

### Phase 3 — Release (runs once)
```
Integration → QA → BugAnalyst → DevOps → Document → Retro
```

### User Interaction Gates

1. **Q&A Gate** (`QA_PENDING`): Pipeline pauses; user answers clarifying questions
2. **Architecture Review Gate** (`ARCHITECTURE_REVIEW_PENDING`): User approves or requests changes
3. **Design Review Gate** (`DESIGN_REVIEW_PENDING`): User approves or requests design revisions; includes Visual Preview
4. **Change Request Gate** (`CHANGE_REQUESTED`): User confirms or cancels requirement changes mid-sprint

---

## Agents (17 registered in AgentFactory + 2 additional)

**Discovery**: StrategicReviewAgent, ProductOwnerAgent, ArchitectAgent, DesignerAgent, SecurityAgent, SprintPlannerAgent

**Sprint** (per sprint): ScrumMasterAgent, FileStructurePlannerAgent, BackendDeveloperAgent, FrontendDeveloperAgent, SprintDeployAgent, SprintReviewAgent

**Release**: IntegrationDeveloperAgent, QAAgent, BugAnalystAgent, DevOpsAgent, DocumentAgent, RetroAgent

**Special** (via container): DomainResearcherAgent (pre-Q&A research), ClarificationAgent (Q&A), ChatRouter (chat)

---

## Auth System

- **JWT access tokens** — 15min expiry, in-memory in frontend
- **Refresh tokens** — stored as SHA-256 hashes in SQLite; persisted in `sessionStorage`
- **RBAC** — roles: `admin` (all projects), `developer` (own projects), `viewer`
- **Project isolation** — `owner_id` enforced on every project-scoped API endpoint
- Toggle: `AUTH_ENABLED=true` in `.env` (default: true)

---

## LLM Configuration

Default: `config/config.yaml`
```yaml
llm:
  provider: ollama
  model: qwen2.5-coder:7b
  base_url: http://localhost:11434
  temperature: 0.1
  max_tokens: 4096
```

Override via `.env`:
```
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
```

Switch at runtime (no restart): `POST /settings/llm`

---

## Memory System (6 stores)

| Store | Purpose | Backend |
|-------|---------|---------|
| MemoryManager | Project-scoped key-value (predecessor messages, design) | SQLite |
| KnowledgeMemory | Semantic vector search (HNSW) | SQLite + hnswlib |
| LearningLoop | Trajectory recording (approved/rejected per stage) | SQLite |
| LessonStore | Human-readable lessons per stage/project | SQLite |
| CheckpointManager | Crash recovery checkpoints | SQLite/JSON |
| CostTracker | Token usage and latency per call | SQLite |

---

## API Routes (20 routers)

All project-scoped routes require JWT auth. Full list in `CURRENT-STATE.md`.

Key endpoints:
- `POST /auth/register` — create account
- `POST /auth/login` — get tokens
- `POST /projects` — create project
- `POST /workflow/start` — run pipeline
- `GET /workflow/{id}/design-review` — get design for review
- `POST /workflow/{id}/design-review` — approve/reject design
- `GET /projects/{id}/download` — ZIP all generated files
- `WS /ws/{project_id}` — real-time pipeline events

---

## Frontend Structure

```
frontend/src/
  App.tsx                     — Router + ProtectedRoute (mandatory login)
  main.tsx                    — React 19 root + AuthProvider
  pages/
    LandingPage.tsx           — Home; redirects logged-in users to /projects
    LoginPage.tsx             — Email+password auth; register link
    ProjectsPage.tsx          — Dashboard + new project modal
    WorkspacePage.tsx         — Full workspace: pipeline/chat/files/logs/artifacts/metrics/changes
    SettingsPage.tsx          — LLM settings
    AnalyticsPage.tsx         — Cost/usage dashboard
    AdminPage.tsx             — User management (admin only)
  components/
    layout/AppLayout.tsx      — Sidebar navigation
    design/DesignReviewModal  — Spec view + visual HTML preview
    [chat/, files/, logview/, metrics/, pipeline/, qa/, ui/]
  lib/
    auth.tsx                  — AuthContext: JWT tokens, login/register/logout
    api.ts                    — Typed API client (Bearer token on all requests)
  hooks/
    useLogs.ts, usePipeline.ts, useWebSocket.ts
```

---

## Known Limitations

1. **Synchronous pipeline** — one LLM call at a time; stages cannot parallelize
2. **Local SQLite** — no multi-instance or horizontal scaling
3. **No frontend tests** — zero Jest/Vitest test files
4. **Missing `transformers` package** — causes 2 test failures in knowledge embedding tests
5. **ContextManager disabled** — intelligence context injection disabled in some paths

---

## Running the System

```bash
# Backend prerequisites
ollama serve
ollama pull qwen2.5-coder:7b

# Install + test
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q

# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` → register → create a project → describe your app → watch it build.

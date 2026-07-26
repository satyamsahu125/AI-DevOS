# Project Overview — AI DevOS

**Last Updated**: 2026-07-27
**Status**: Functionally complete multi-agent pipeline
**System Version**: 1.1 (post-sprint-sync, post-intelligence-layer)

---

## What This Project Does

AI DevOS is a **multi-agent software engineering pipeline** that transforms natural-language project
descriptions into real, downloadable, runnable source code.

Describe an application in plain English -> 15 specialized AI agents (each backed by LLM + schema
validation + automated reviewer) -> download real source files -> run the generated project.

Unlike asking an LLM to write an app in one shot, AI DevOS:
- **Stages the work** across 15 specialized agents with clear responsibility separation
- **Reviews each stage** with a three-tier gate (AUTO_FIX/ASK_HUMAN/FLAG) before the next stage runs
- **Generates real files** — Backend/Frontend code written to disk, not JSON artifacts
- **Learns from experience** via trajectory recording, knowledge embedding, and lesson storage
- **Resumes on crash** — ProjectState persisted on every transition; resumes from last saved state
- **Manages requirement changes** — Impact analysis identifies affected stages; only re-runs what changed

---

## System Architecture

### High-Level Topology

```
Frontend (Vite + React 19 + TypeScript, :5173)
  | HTTP via Vite proxy to localhost:8000 — no CORS config needed
  v
Backend (FastAPI, :8000)
  +- DI Container (kernel/container.py)
  |    Singletons: WorkflowManager, LLMManager, ArtifactManager,
  |                MemoryManager, KnowledgeMemory, LearningLoop,
  |                WorkflowEngine, SprintMonitor, ContextOrchestrator, ...
  +- 15-Stage WorkflowManager (workflow/manager.py)
  |    -> WorkflowEngine: execute -> review -> retry
  |         -> AgentFactory: creates agent per stage
  |         -> LLMManager: routes to Ollama or AWS Bedrock
  |         -> Reviewer: three-tier quality gates
  +- Memory System
  |    MemoryManager (SQLite), KnowledgeMemory (HNSW vectors),
  |    LearningLoop (trajectories), LessonStore, CheckpointManager
  +- Intelligence Layer
  |    FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator
  +- Events
       EventBroadcaster -> WebSocket /ws/{project_id}
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend runtime | Python 3.10+, FastAPI (fully synchronous pipeline path) |
| Frontend | Vite 8, React 19, TypeScript 6, Tailwind CSS v4 |
| LLM (default) | Ollama local server, model: qwen2.5-coder:7b |
| LLM (alternate) | AWS Bedrock Runtime Converse API (Claude 3.5 Sonnet) |
| Storage | SQLite (artifacts, memory, trajectories, lessons, file index, costs) |
| Vector search | HNSW (hnswlib) for knowledge embedding |
| Package manager | pip (backend), npm/vite (frontend) |

---

## The Pipeline: 15 Stages + State Machine

### Pipeline States (ProjectState enum — 24 values)

```
EMPTY -> CLARIFYING -> QA_PENDING -> QA_IN_PROGRESS -> REQUIREMENTS_READY
  -> ARCHITECTURE_READY -> DESIGN_READY -> DESIGN_REVIEW_PENDING -> DESIGN_APPROVED
  -> SPRINT_PLAN_READY -> SPRINT_IN_PROGRESS -> ALL_SPRINTS_COMPLETE
  -> QA_COMPLETE -> DEPLOYABLE | DONE | FAILED | PAUSED
Change path: CHANGE_REQUESTED -> RESUMING_FROM_CHANGE -> SPRINT_IN_PROGRESS
```

### Stages (verified from agents/factory.py and shared/enums/stage.py)

| # | Stage Name | Agent | Purpose |
|---|-----------|-------|---------|
| 0 | DomainResearch | DomainResearcherAgent | Research domain before Q&A |
| 1 | Clarification | ClarificationAgent | Generate Q&A; process answers |
| 2 | StrategicReview | StrategicReviewAgent | Validate project feasibility |
| 3 | ProductOwner | ProductOwnerAgent | Draft structured requirements |
| 4 | Architect | ArchitectAgent | System architecture spec |
| 5 | Designer | DesignerAgent | UI/UX design spec (user gate) |
| 6 | Security | SecurityAgent | Security review |
| 7 | SprintPlanning | SprintPlannerAgent | Sprint breakdown |
| 8 | ScrumMaster | ScrumMasterAgent | Task breakdown per sprint |
| 9 | FileStructurePlanner | FileStructurePlannerAgent | File plan per sprint |
| 10 | BackendDeveloper | BackendDeveloperAgent | Generate backend source files |
| 11 | FrontendDeveloper | FrontendDeveloperAgent | Generate frontend source files |
| 12 | QA | QAAgent | Test plan and QA report |
| 13 | DevOps | DevOpsAgent | Deployment configuration |
| 14 | Document | DocumentAgent | Project documentation |
| 15 | Retro | RetroAgent | Sprint retrospective |

Note: DomainResearch and Clarification are pre-planning stages. Stages 9-11 run inside each sprint loop.

### User Interaction Gates

1. **Q&A Gate** (QA_PENDING): Pipeline pauses; user answers clarifying questions
2. **Design Review Gate** (DESIGN_REVIEW_PENDING): User approves or requests design revisions
3. **Change Request Gate** (CHANGE_REQUESTED): User confirms or cancels requirement changes

---

## Agents (15 registered in AgentFactory + 2 additional)

From agents/factory.py:
- product_owner, architect, backend, frontend, qa, devops
- strategic_review, designer, security, file_planner, document
- retro, clarification, sprint_planner, scrum_master

From container (not in factory):
- DomainResearcherAgent (resolved as domain_researcher_agent)
- ChatRouter (resolved as chat_router — not a pipeline agent)

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
AWS_BEARER_TOKEN_BEDROCK=...
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

Note: ContextManager and MemoryOrchestrator are implemented but DISABLED in the live container.

---

## API Routes (14 routers)

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| health | / | GET /ready, GET /health |
| project | /projects | CRUD projects |
| workflow | /workflow | POST /start, GET/POST /design-review, POST /stop |
| websocket | /ws, /api/ws | WebSocket /ws/{project_id} |
| chat | /chat | POST chat messages |
| artifacts | /artifacts | GET artifacts per project/stage |
| agents | /agents | Agent info |
| memory | /memory | Memory store access |
| learning | /learning | Learning stats |
| files | /files | Generated project file browsing |
| logs | /logs | Pipeline execution logs |
| settings | /settings | LLM settings + runtime config |
| intelligence | /intelligence | File index, dependency graph, code summaries |

---

## Frontend Structure

```
frontend/src/
  App.tsx              — Router: /projects + /projects/:projectId
  main.tsx             — React 19 root
  pages/
    ProjectsPage.tsx   — Dashboard + new project modal
    WorkspacePage.tsx  — Full workspace UI
  components/          — chat/, design/, files/, logview/, metrics/, pipeline/, qa/, ui/
  hooks/               — useLogs.ts, usePipeline.ts, useWebSocket.ts
  lib/api.ts           — Typed API client (all calls via /api prefix)
```

---

## Known Limitations

1. **Single-user only** — no authentication or RBAC
2. **Synchronous pipeline** — one LLM call at a time; cannot parallelize stages
3. **Local SQLite** — no multi-instance or horizontal scaling
4. **No frontend tests** — zero Jest/Vitest test files
5. **Missing `transformers` package** — causes test failures when touching KnowledgeMemory embedding
6. **ContextManager disabled** — intelligence context injection not active in some paths
7. **Version pinning** — auto-detected dependencies in generated projects have `# TODO: pin version`

---

## Running the System

```bash
# Prerequisites
ollama serve
ollama pull qwen2.5-coder:7b

# Install + test
pip install -r backend/requirements.txt
cd backend && python -m pytest tests/ -q

# Start
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload  # backend
npm run dev                                                  # frontend (separate terminal)
```

Or use `run.sh` (checks Ollama, installs deps, runs tests, starts server).

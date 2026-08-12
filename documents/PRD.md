# Product Requirements Document (PRD) — Reverse-Engineered Baseline

> **Audit Context**: Derived exclusively from static and architectural inspection of the codebase in `backend/` and `frontend/`.

---

## 1. Product Overview

**AI DevOS** is an autonomous multi-agent software development platform that converts natural language requirements or strategic briefs into functional, tested, containerized software projects. 

It provides an end-to-end multi-agent orchestration lifecycle where specialized AI agents (Product Owner, Architect, Designer, Security Specialist, Sprint Planner, Tech Lead / Scrum Master, Backend Developer, Frontend Developer, QA Engineer, Bug Analyst, DevOps Engineer) work sequentially and iteratively to generate source code, run sandboxed tests, write documentation, and track retro feedback.

---

## 2. Intended Users & Personas

1. **Software Architect / Lead Engineer**: Leverages AI DevOS to generate structured project boilerplate, requirement specs, design models, and architecture documents.
2. **Product Manager**: Submits strategic requirements briefs, reviews clarification questions, and tracks sprint progress through interactive UI dashboards.
3. **Full-Stack Developer**: Reviews multi-agent generated code, monitors automated build/test runs, and provides interactive feedback or approval decisions.
4. **DevOps / System Administrator**: Manages containerized deployments, inspects Prometheus metrics, and manages API keys and distributed OpenTelemetry traces.

---

## 3. Core Capabilities Matrix

### 3.1 Requirement Clarification & Strategy [IMPLEMENTED]
- **Clarification Stage**: Pre-planning interactive Q&A router (`app/workflow/stage_runner.py`, `app/shared/schemas/clarification_schema.py`) to resolve ambiguous user requirements.
- **Strategic Brief Generation**: Evaluates domain requirements, business goals, target audience, and risk factors.

### 3.2 Multi-Agent Software Development Pipeline [IMPLEMENTED]
- **Sequential Pipeline**: Executes `clarification` → `strategic_review` → `product_owner` → `architect` → `designer` → `security` → `sprint_planner` → `sprint_stages` (Scrum Master, Sprint Delta, File Planner, Backend, Frontend, Sprint Deploy, Sprint Review) → `integration` → `qa` → `bug_analyst` → `devops` → `document` → `retro`.
- **Sprint-Scoped File Delta Generation**: On Sprint 2+, `SprintDelta` classifies target files into `create`, `update`, `patch` operations (`app/shared/schemas/sprint_delta_schema.py`).
- **File Structure & Code Synthesis**: `FileStructurePlanner` formulates precise file paths and tech stack allocations; `BackendDeveloper` and `FrontendDeveloper` generate code file-by-file with syntax validation before writing.

### 3.3 Containerized Execution & Build Validation [IMPLEMENTED]
- **Phase1 / Phase5 Docker Sandbox**: Executes generated code inside isolated Docker containers (`app/execution/docker_sandbox.py`, `app/execution/runner.py`).
- **Import Resolution & Smoke Testing**: `SprintDeploy` runs sanity checks on generated files, verifies dependency manifests, and reports build/deploy status (`DeployResult`).

### 3.4 Quality Assurance & Intelligent Bug Analysis [IMPLEMENTED]
- **QA Orchestrator**: Generates unit/integration test suites and executes them (`app/workflow/qa_orchestrator.py`).
- **Bug Analyst**: Evaluates test failure tracebacks, isolates root causes, and feeds structured bug analysis back into the replanning loop.

### 3.5 Memory, Lessons & RAG System [IMPLEMENTED]
- **Multi-Level Memory Architecture**: Working memory, long-term memory, sprint-scoped memory, and global knowledge base.
- **HNSW Vector Retrieval**: `hnswlib` vector index for semantic similarity search over historical lessons, past bugs, and code snippets (`app/memory/hnsw_memory_store.py`).
- **Learning Middleware**: Captures stage output patterns and automatically indexes success/failure lessons into SQLite databases (`lessons.sqlite`, `learning.sqlite`, `knowledge.sqlite`).

### 3.6 Human-in-the-Loop Gate Reviews [IMPLEMENTED]
- **Reviewer System**: Supports `Approved` and `Rejected` decisions at designated workflow checkpoints (`app/review/manager.py`, `app/api/gates.py`).
- **Change Management & Replanning Router**: Routes reviewer rejection back to impacted stages or requirement versioning (`app/workflow/change_manager.py`).

### 3.7 Observability & Telemetry [IMPLEMENTED]
- **Structured Logging**: `structlog` integration with request ID and project ID contextual binding.
- **Distributed Tracing**: OpenTelemetry instrumentation with Jaeger/OTLP export support (`app/observability/tracing.py`).
- **Prometheus Metrics**: FastAPI instrumentation serving `/metrics` endpoint (`app/observability/prometheus.py`).

---

## 4. Feature Implementation Breakdown

| Feature | Status | Evidence File(s) |
| --- | --- | --- |
| FastAPI REST & WS Server | `IMPLEMENTED` | `backend/app/main.py`, `backend/app/api/router.py` |
| Multi-Stage Pipeline Execution | `IMPLEMENTED` | `backend/app/workflow/engine.py`, `backend/app/workflow/stage_runner.py` |
| Sprint-Scoped Code Synthesis | `IMPLEMENTED` | `backend/app/workflow/sprint_executor.py` |
| Celery + Redis Asynchronous Task Queue | `IMPLEMENTED` | `backend/app/tasks/pipeline_task.py`, `backend/docker-compose.yml` |
| In-Process Background Task Fallback | `IMPLEMENTED` | `backend/app/workflow/engine.py` (when Redis is down) |
| SQLite Multi-Database Storage | `IMPLEMENTED` | `backend/app/storage/sqlite_storage_adapter.py`, `backend/data/` |
| Alembic Schema Migrations | `IMPLEMENTED` | `backend/migrations/versions/0001_initial_baseline.py` |
| HNSW Vector Index & Embeddings | `IMPLEMENTED` | `backend/app/memory/hnsw_memory_store.py` |
| LLM Provider Abstraction (Multi-Provider) | `IMPLEMENTED` | `backend/app/llm/manager.py`, `backend/app/llm/providers/` |
| Docker Sandbox Container Execution | `IMPLEMENTED` | `backend/app/execution/docker_sandbox.py` |
| JWT Authentication & API Key Middleware | `IMPLEMENTED` | `backend/app/api/middleware/auth.py`, `backend/app/api/auth.py` |
| Rate Limiting & Request Size Middleware | `IMPLEMENTED` | `backend/app/api/middleware/rate_limit.py`, `request_size.py` |
| React + Vite Frontend Dashboard | `IMPLEMENTED` | `frontend/src/App.tsx`, `frontend/src/pages/WorkspacePage.tsx` |
| Real-time WebSocket Log Streaming | `IMPLEMENTED` | `backend/app/api/websocket.py`, `frontend/src/hooks/useWebSocket.ts` |
| Automated OpenTelemetry & Prometheus Tracing | `IMPLEMENTED` | `backend/app/observability/` |
| Multi-Model Fallback Chain | `PARTIAL` | Provider fallback structure exists in `llm/manager.py` but fallback rules are basic |
| Fine-Grained Role-Based Access Control (RBAC) | `PARTIAL` | `admin` flag in `auth.db` user table exists, but API endpoint protection uses coarse bearer/API-key checks |
| Live Preview Container Web Server | `PARTIAL` | `preview.py` router exists, returns container port mappings, but lacks live hot-reloading web proxy |
| Direct Git Remote Push / Sync | `STUB` / `PARTIAL` | `git_manager.py` manages local git repos in project workspace; external remote pushing is minimal |

---

## 5. Non-Goals

1. **General-Purpose Code Editor**: AI DevOS is not an IDE replaced web browser editor. It is an autonomous workflow engine that writes complete files into a target workspace repository.
2. **Infinite Autonomous Loop without Budget**: AI DevOS does not run uncontrolled loops; token budgets, retry policies, and reviewer gates strictly bound execution.

---

## 6. Current Limitations & Constraints

- **Single Worker Concurrency Default**: Docker Compose defaults to `concurrency=2` for Celery workers. High-volume parallel project runs require scaling Celery workers.
- **Local Embedding Latency**: `sentence-transformers` running on CPU inside container may add 100-300ms overhead during embedding generation if GPU is unavailable.
- **Workspace Disk Persistence**: Generated projects live under `./temp-workspace/<project_id>/` on the host filesystem.

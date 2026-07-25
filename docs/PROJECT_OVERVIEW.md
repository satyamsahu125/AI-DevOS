# Project Overview — AI DevOS v1.1

**Last Updated**: 2026-07-25  
**Status**: Production-Ready (v1.1)  
**System Maturity**: Multi-agent pipeline generating real code (12 stages)

---

## What This Project Does

AI DevOS is a **production-grade, 12-stage multi-agent software engineering pipeline** that transforms natural-language project descriptions into real, downloadable, runnable source code.

### Key Capability
Describe an application in plain English → 12 specialized AI agents (each backed by LLM + schema validation + automated reviewer) → Download real source files → Run the generated project

Unlike asking an LLM to write an app in one shot, AI DevOS:
- **Stages the work** across 12 specialized agents, each with a clear responsibility
- **Reviews each stage** with a three-tier gate (AUTO_FIX/ASK_HUMAN/FLAG) before the next stage runs
- **Generates real files**, not JSON artifacts — Backend/Frontend code is actually written to disk
- **Learns from experience** via trajectory recording, knowledge embedding, and lesson storage
- **Resumes on crash** — if the backend restarts mid-pipeline, resume from the last completed stage

---

## System Architecture

### High-Level Topology

```
Frontend (Vite + React 19 + TypeScript, :5173)
  ↓ (HTTP via Vite proxy, no CORS needed)
Backend (FastAPI, :8000)
  ├─ DI Container (singletons: managers, registries)
  ├─ 12-Stage Workflow Engine (execute → review → retry)
  │   ├─ Agent Factory (creates agents per stage)
  │   ├─ LLM Manager (routes to Ollama or AWS Bedrock)
  │   ├─ Reviewer (three-tier quality gates)
  │   ├─ Memory System (6 distinct stores)
  │   └─ Project Workspace (isolated per project_id)
  └─ SQLite (artifacts, memory, trajectories, lessons)
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI (synchronous end-to-end) |
| **Frontend** | Vite, React 19, TypeScript, Tailwind CSS v4 |
| **LLM Providers** | Ollama (local, default qwen2.5-coder:7b) or AWS Bedrock (switchable at runtime) |
| **Storage** | SQLite (single-instance), HNSW vector index for knowledge embeddings |
| **Architecture** | Synchronous pipeline (deliberate choice, no asyncio in execution path) |

---

## The 12-Stage Pipeline

Each stage is a specialized agent that transforms its input into validated output:

| # | Stage | Agent | Input | Output | Purpose |
|---|-------|-------|-------|--------|---------|
| 1 | **Strategic Review** | StrategicReviewAgent | Raw request | Go/no-go assessment | Validate request viability |
| 2 | **Product Owner** | ProductOwnerAgent | Requirements analysis | User stories, acceptance criteria | Extract product vision |
| 3 | **Architect** | ArchitectAgent | Requirements | System architecture, APIs, data models | Design system blueprint |
| 4 | **Designer** | DesignerAgent | Architecture | UI/UX design spec, pages, components | Define user experience |
| 5 | **Security** | SecurityAgent | Design | Security review, threats, mitigations | Identify security risks |
| 6 | **File Planner** | FileStructurePlannerAgent | All above | Concrete file list (path, module, purpose) | Plan file generation |
| 7 | **Backend Developer** | BackendDeveloperAgent | File plan + context | Real backend source files | Generate backend code |
| 8 | **Frontend Developer** | FrontendDeveloperAgent | File plan + design | Real frontend source files | Generate frontend code |
| 9 | **QA** | QAAgent | Generated code | Test plan, bug list | Plan testing |
| 10 | **Document** | DocumentAgent | All artifacts | Project documentation | Write user guides |
| 11 | **DevOps** | DevOpsAgent | Code + security review | Deployment guidance | Plan deployment |
| 12 | **Retro** | RetroAgent | All above | Lessons learned | Extract insights |

**Key Design**: Only stages 7-8 write to disk. All others produce reviewable documents that downstream stages read as context.

---

## Core Components

### Workflow Management
- **WorkflowEngine**: Execute → Review → Retry cycle (3 retries max per stage)
- **WorkflowManager**: State machine orchestrator (resume-safe)
- **DependencyGraph**: Stage ordering (12-stage DAG)
- **ExecutionStateRegistry**: Tracks running/paused/stopped status

### Quality Assurance
- **Reviewer**: Three-tier (AUTO_FIX mechanical / ASK_HUMAN blocks approval / FLAG advisory)
- **ReviewRules**: 23+ validation checkpoints
- **SafetyPolicy**: Prevents writes outside workspace_root

### Memory System (6 Stores)
1. **MemoryManager**: Latest predecessor message handoff (per-key single-slot)
2. **ArtifactManager**: Every attempt history + approval status (permanent)
3. **LearningLoop**: Trajectory stats (permanent)
4. **KnowledgeMemory**: Semantic search over approved trajectories (HNSW vector index)
5. **LessonStore**: Human-readable learned lessons (permanent, prunable at 90d)
6. **ProjectEventLog**: Live output stream (operational log)

### LLM Integration
- **LLMManager**: Provider abstraction + cost tracking
- **OllamaProvider**: HTTP to local Ollama (default)
- **BedrockProvider**: AWS Bedrock Runtime (runtime-switchable via `/settings/llm`)
- **ProviderHealth**: Model availability checks

### Project Isolation
- **ProjectManager**: Create + initialize projects
- **WorkspaceManager**: Per-project `temp-workspace/{id}/` isolation
- **ProjectFileManager**: Sanitized path writes + `..` traversal protection
- **DependencyDetector**: Auto-generates `package.json`/`requirements.txt` from imports

### API Layer (10 Routes)
- `/health`, `/ready` — Health checks
- `/projects` — CRUD operations
- `/workflow/start`, `/workflow/{id}/stop` — Pipeline control
- `/artifacts` — View approved outputs
- `/agents` — Introspection
- `/memory/{project_id}` — Query memory stores
- `/files`, `/download`, `/run-instructions` — Download generated code
- `/logs` — Live output tailing
- `/settings/llm` — Provider switching

---

## Key Features

✅ **Real Code Generation**
- One LLM call per file (not one call for entire app)
- Syntax validation before writing
- Auto-generated dependency manifests (package.json, requirements.txt)

✅ **Staged Review**
- Three-tier gates (AUTO_FIX/ASK_HUMAN/FLAG)
- 23+ validation rules
- Feedback injected into retry prompts

✅ **Crash-Safe Resume**
- Checkpoint manager saves pre-execution state
- Pipeline resumes from last completed stage
- No need to re-run all 12 stages after interruption

✅ **Learning System**
- Every attempt (approved/rejected) logged to trajectories
- Approved trajectories embedded into knowledge base
- Semantic search surfaces "what worked before"
- Human-readable lessons extracted per approval

✅ **LLM Provider Flexibility**
- Ollama (local model, default qwen2.5-coder:7b)
- AWS Bedrock (cloud-based alternatives)
- Runtime switching via `/settings/llm` (no restart needed)
- Provider switch persisted to `.env`

✅ **Project Isolation**
- Every project gets isolated workspace, memory namespace, artifact directory
- Two projects never see each other's state
- Supports concurrent project runs

✅ **Comprehensive Testing**
- 42 test files, ~194 tests passing
- Coverage: workflow pipeline, agents, memory, LLM integration, file operations, API endpoints

---

## Known Limitations

⚠️ **Version Pinning Not Implemented**
- Generated `package.json` uses `*` (npm), `requirements.txt` has no versions
- Builds not reproducible across time
- Workaround: Use lockfiles (package-lock.json, poetry.lock)

⚠️ **Single-Process Only**
- No horizontal scaling built-in
- Synchronous LLM calls block (not async)
- Scale via clustering/multiple instances (future work)

⚠️ **No Authentication/RBAC**
- Single-user deployments only
- No multi-tenant isolation
- Auth layer planned for future

⚠️ **Stop Signal Limitations**
- Can't interrupt in-flight LLM calls (blocking HTTP)
- Takes effect between retry attempts/stages
- Workaround: Restart backend (resumes from checkpoint)

⚠️ **Polling-Based Frontend**
- Live updates via polling (3-4s latency)
- WebSockets not yet implemented
- Works fine for single-user, not ideal for many concurrent users

---

## Development Status

**Version 1.1** (Current)
- ✅ All 12 stages fully implemented and wired
- ✅ Real code generation (Backend/Frontend agents)
- ✅ Three-tier review gates
- ✅ Crash-safe resume via checkpoints
- ✅ Learning loop + knowledge embedding
- ✅ AWS Bedrock provider support
- ✅ Project isolation
- ✅ Comprehensive testing
- ⚠️ 7 critical issues found in audit (see AUDIT_FINAL_FINDINGS.md)

**Series A Readiness**
- System is fundamentally sound
- 7 critical issues must be fixed before Series A (2-3 weeks)
- High-priority improvements planned for next sprint

---

## Folder Overview

```
backend/               # Python FastAPI application
├── app/
│   ├── agents/       # 12 stage agents + 2 auxiliary
│   ├── actions/      # LLM-backed action classes
│   ├── api/          # 10 HTTP route modules
│   ├── workflow/     # Pipeline orchestration
│   ├── memory/       # 6 memory stores
│   ├── llm/          # LLM provider abstraction
│   ├── prompt/       # 12 stage-specific prompt builders
│   ├── execution/    # Stage execution engine
│   ├── review/       # Three-tier review system
│   ├── project/      # Project management
│   ├── workspace/    # File I/O + isolation
│   ├── kernel/       # Bootstrap + DI container
│   └── shared/       # Schemas, DTOs, exceptions, enums
├── tests/            # 42 test files
└── requirements.txt  # Dependencies

frontend/             # Vite + React application
├── src/
│   ├── components/   # UI components
│   ├── pages/        # Route pages
│   ├── hooks/        # Custom hooks
│   ├── lib/          # API client + utilities
│   └── styles/       # CSS
├── public/
└── package.json

docs/                 # Project documentation
├── CURRENT-STATE.md          # Authoritative system description ✅
├── COMMANDS.md               # Setup, run, test commands
├── AUDIT_*.md               # Architecture audit reports (new)
├── PROJECT_OVERVIEW.md       # This file
├── STAGE-FLOW.md            # Stage definitions (outdated)
├── ROADMAP.md               # Implementation roadmap (outdated)
└── ...other docs
```

---

## Getting Started

See `COMMANDS.md` for:
- Prerequisites (Python 3.12+, Node 18+, Ollama or AWS Bedrock)
- Backend setup + startup
- Frontend setup + startup
- Running tests
- One-off API calls

---

## For More Details

- **Architecture Deep Dive**: Read `CURRENT-STATE.md` (the authoritative description)
- **Critical Issues Found**: Read `AUDIT_FINAL_FINDINGS.md` (7 issues, 2-3 week fix timeline)
- **Technical Debt Inventory**: Read `AUDIT_TECH_DEBT.md` (31 issues total)
- **Component Status Matrix**: Read `AUDIT_COMPONENT_INDEX.md` (52 components catalogued)

---

## Next Steps

**For Series A**: Fix 7 critical issues (2-3 weeks) → Re-audit → Proceed with funding

**For Production Scale**: Add async execution, PostgreSQL, Redis cache, horizontal scaling

**For Enterprise Features**: Add authentication/RBAC, multi-model support, advanced analytics


# AI DevOS — Current Implementation State

_Last updated: 2026-07-27. Verified against actual source files — not aspirational plans._
_This document supersedes all earlier state descriptions for "what actually runs today."_

---

## 1. Objective

AI DevOS is a multi-agent software engineering pipeline. A user describes an application in plain
English; 15 specialized AI agents (each backed by an LLM call, structured-output schema, and
automated reviewer) carry it from idea to a downloadable, runnable codebase.

---

## 2. High-level Architecture

```
Frontend (Vite + React 19 + TS, :5173)
  | Vite proxy -> localhost:8000 (no CORS config)
  v
Backend (FastAPI, :8000)
  +- DI Container (kernel/container.py)
  |    ~40 singletons; all wired in Container.build()
  +- WorkflowManager (workflow/manager.py — 881 lines)
  |    State machine over 24 ProjectState values
  |    Calls WorkflowEngine per stage
  +- WorkflowEngine (workflow/engine.py)
  |    execute -> review -> retry loop
  |    Injects: predecessor message, design context, lessons, patterns, intelligence context
  +- AgentFactory (agents/factory.py)
  |    15 agents registered; creates one per stage call
  +- LLMManager (llm/manager.py)
  |    OllamaProvider (default) or BedrockProvider; runtime-switchable
  +- Reviewer (review/reviewer.py)
  |    Three-tier: AUTO_FIX / ASK_HUMAN / FLAG
  +- Memory System (6 SQLite stores)
  +- Intelligence Layer (FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator)
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
| App entry | app/main.py (42 lines) | LIVE | lifespan wires broadcaster |
| DI Container | kernel/container.py | LIVE | 40+ singletons |
| WorkflowManager | workflow/manager.py (881 lines) | LIVE | full state machine |
| WorkflowEngine | workflow/engine.py | LIVE | execute/review/retry |
| WorkflowStateMachine | workflow/state_machine.py | LIVE | 5 workflow states |
| RetryPolicy | workflow/retry_policy.py | LIVE | configurable max_retries |
| ExecutionManager | execution/manager.py | LIVE | thin shell over engine |
| ExecutionEngine | execution/engine.py | LIVE | runs one stage |

### Agents (15 registered in AgentFactory)

| Agent | Registration Key | Status |
|-------|----------------|--------|
| ProductOwnerAgent | product_owner | LIVE |
| ArchitectAgent | architect | LIVE |
| BackendDeveloperAgent | backend | LIVE |
| FrontendDeveloperAgent | frontend | LIVE |
| QAAgent | qa | LIVE |
| DevOpsAgent | devops | LIVE |
| StrategicReviewAgent | strategic_review | LIVE |
| DesignerAgent | designer | LIVE |
| SecurityAgent | security | LIVE |
| FileStructurePlannerAgent | file_planner | LIVE |
| DocumentAgent | document | LIVE |
| RetroAgent | retro | LIVE |
| ClarificationAgent | clarification | LIVE |
| SprintPlannerAgent | sprint_planner | LIVE |
| ScrumMasterAgent | scrum_master | LIVE |
| DomainResearcherAgent | (via container only) | LIVE |
| ChatRouter | (via container only) | LIVE |

### LLM Layer

| Component | Status | Notes |
|-----------|--------|-------|
| LLMManager | LIVE | runtime reconfigure via POST /settings/llm |
| OllamaProvider | LIVE | 600s timeout; /api/generate; /api/tags health |
| BedrockProvider | LIVE | Bearer-token auth; AWS Bedrock Runtime |
| LLMFactory | LIVE | creates provider by name |
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
| ContextManager | DISABLED | commented out in container.py — not integrated |
| MemoryOrchestrator | DISABLED | name collision bug (self.store); commented out in container |

### Intelligence Layer

| Component | Status | Notes |
|-----------|--------|-------|
| FileIndexer | LIVE | db: backend/app/memory/file_index.db (hardcoded) |
| DependencyGraph | LIVE | built on FileIndexer |
| CodeSummarizer | LIVE | built on FileIndexer |
| ContextOrchestrator | LIVE | wired into WorkflowEngine; skips gracefully on error |
| SprintMonitor | LIVE | validate_sprint_output + generate_sprint_brief |
| ImpactAnalyzer | LIVE | stage-level + file-level impact analysis |

### API Layer (14 sub-routers)

| Router | Status |
|--------|--------|
| health | LIVE |
| project | LIVE |
| workflow | LIVE |
| websocket | LIVE |
| chat | LIVE |
| artifacts | LIVE |
| agents | LIVE |
| memory | LIVE |
| learning | LIVE |
| files | LIVE |
| logs | LIVE |
| settings | LIVE |
| intelligence | LIVE |

### Events

| Component | Status | Notes |
|-----------|--------|-------|
| EventBroadcaster | LIVE | thread-safe; bind_loop at lifespan startup |
| WebSocket manager | LIVE | multi-tab per project; dead connection cleanup |

### Frontend

| Component | Status | Notes |
|-----------|--------|-------|
| App.tsx (router) | LIVE | /projects + /projects/:id |
| ProjectsPage | LIVE | dashboard + new project modal |
| WorkspacePage | LIVE | pipeline, chat, files, logs, artifacts, metrics |
| lib/api.ts | LIVE | typed client; all calls via /api prefix |
| Frontend tests | MISSING | no Jest/Vitest configured |

---

## 4. Pipeline State Machine (24 states)

```
EMPTY -> CLARIFYING -> QA_PENDING <-> QA_IN_PROGRESS -> QA_COMPLETE
  -> REQUIREMENTS_READY -> ARCHITECTURE_READY -> DESIGN_READY
  -> DESIGN_REVIEW_PENDING -> DESIGN_APPROVED
  -> SPRINT_PLAN_READY -> SPRINT_IN_PROGRESS -> SPRINT_COMPLETE
  -> ALL_SPRINTS_COMPLETE -> QA_COMPLETE -> DEPLOYABLE -> DONE

Special: CHANGE_REQUESTED -> IMPACT_ANALYZED -> REPLANNING -> RESUMING_FROM_CHANGE
         AWAITING_HUMAN_APPROVAL (enum defined; not yet wired in pipeline)
Terminal: FAILED, PAUSED
```

Note: AWAITING_HUMAN_APPROVAL, IMPACT_ANALYZED, and REPLANNING exist in the enum but
are not active states in WorkflowManager.run(). The unhandled state catch logs an error
and returns a FAILED-like PipelineResult without transitioning to FAILED.

---

## 5. Known Issues and Limitations

| ID | Issue | Severity | Status |
|----|-------|---------|--------|
| N1 | Missing `transformers` package in requirements.txt | HIGH | OPEN |
| N2 | Stale test: Fix009ScrumMasterInjection (2 tests) | MEDIUM | OPEN |
| N3 | Stale test: test_pipeline_runs_every_stage_in_order | MEDIUM | OPEN |
| N4 | ContextManager disabled | LOW | OPEN |
| N5 | MemoryOrchestrator name collision bug unresolved | LOW | OPEN |
| N6 | Hardcoded DB paths in container.py | LOW | OPEN |
| G1 | Zero frontend tests | HIGH | OPEN |
| G2 | No E2E / integration tests | HIGH | OPEN |
| G3 | No authentication/RBAC | HIGH | BY DESIGN (single-user) |
| G4 | Synchronous pipeline — no parallelism | MEDIUM | BY DESIGN |
| G5 | SQLite only — no multi-instance | MEDIUM | FUTURE |

---

## 6. Configuration

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

### .env overrides (via python-dotenv)
All LLM_PROVIDER, OLLAMA_*, AWS_* settings; DB paths; REQUIRE_HUMAN_APPROVAL; SKIP_QA.

---

## 7. Test Status (2026-07-27)

- Total collected: 377 tests, 47 files
- Subset run (3 long suites excluded): 57 passed, 4 failed
- Root causes of failures: 2 (missing transformers package; 2 stale test classes)
- Long suites (test_sprint_sync, test_project_intelligence, test_project_file_generation): not timed — exceed 45s run window

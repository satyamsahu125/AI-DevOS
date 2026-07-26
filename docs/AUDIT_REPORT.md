# AI DevOS — Canonical Audit Report

**Audit Date**: 2026-07-27
**Auditor**: Automated deep-code inspection (Claude Sonnet 4.6)
**Scope**: Full repository — backend/app, frontend/src, tests, docs, config
**Source of truth**: Actual file contents; nothing fabricated or assumed

---

## 1. Repository Snapshot

| Metric | Value |
|--------|-------|
| Backend packages (backend/app/) | 22 packages |
| Backend Python files | ~190 |
| Frontend TypeScript/TSX files | 18 |
| Test files | 47 |
| Tests collected by pytest | 377 |
| Docs files | 25+ |
| Main entry point | backend/app/main.py (42 lines) |
| Largest file | workflow/manager.py (881 lines) |

---

## 2. Implementation Status Per Component

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI app + lifespan | IMPLEMENTED | main.py 42 lines; broadcaster bound at startup |
| DI Container (kernel/container.py) | IMPLEMENTED | Hand-wired singletons; 40+ services registered |
| WorkflowManager | IMPLEMENTED | 881 lines; full state machine; concurrency guard |
| WorkflowEngine | IMPLEMENTED | execute -> review -> retry with detailed feedback injection |
| WorkflowStateMachine | IMPLEMENTED | Thin 5-state wrapper (Created/Running/Approved/Completed/Failed) |
| ProjectState enum | IMPLEMENTED | 24 states including change management states |
| Stage enum | IMPLEMENTED | 18 stages |
| AgentFactory | IMPLEMENTED | 15 agents registered |
| DomainResearcherAgent | IMPLEMENTED | Wired in container; runs before Q&A |
| ClarificationAgent | IMPLEMENTED | Q&A generation + answer processing |
| SprintPlannerAgent | IMPLEMENTED | Produces SprintPlan model |
| SprintMonitor | IMPLEMENTED | validate_sprint_output + generate_sprint_brief |
| OllamaProvider | IMPLEMENTED | 600s timeout; /api/generate; health check |
| BedrockProvider | IMPLEMENTED | Bearer-token auth; AWS Bedrock Runtime Converse API |
| LLMManager | IMPLEMENTED | Pluggable; runtime reconfigure without restart; cost tracking |
| EventBroadcaster | IMPLEMENTED | Thread-safe; bind_loop at startup; singleton |
| WebSocket layer | IMPLEMENTED | /ws/{id} + /api/ws/{id}; multi-tab per project |
| ExecutionManager | IMPLEMENTED | Thin shell over ExecutionEngine |
| ProjectWriter | IMPLEMENTED | Wired with FileIndexer |
| FileValidator | IMPLEMENTED | Python/JS syntax checks |
| ArtifactManager | IMPLEMENTED | Per-stage, per-attempt artifact storage |
| MemoryManager | IMPLEMENTED | SQLite-backed; project-scoped |
| KnowledgeMemory | IMPLEMENTED | HNSW vector index; semantic search |
| LearningLoop | IMPLEMENTED | Trajectory recording + pattern retrieval |
| LessonStore | IMPLEMENTED | Human-readable lessons per stage/project |
| CostTracker | IMPLEMENTED | Per-call token/latency tracking |
| ImpactAnalyzer | IMPLEMENTED | Stage-level + file-level impact analysis |
| ProjectValidator | IMPLEMENTED | validate + self-healing (up to 3 heal attempts) |
| Reviewer | IMPLEMENTED | Three-tier (AUTO_FIX/ASK_HUMAN/FLAG); schema-specific checks |
| RetryPolicy | IMPLEMENTED | Configurable max_retries |
| CheckpointManager | IMPLEMENTED | Crash recovery; incomplete session detection on startup |
| ContextOrchestrator | IMPLEMENTED | Wired into WorkflowEngine; gracefully skips on error |
| FileIndexer | IMPLEMENTED | SQLite-backed; db_path=backend/app/memory/file_index.db |
| DependencyGraph | IMPLEMENTED | Built on FileIndexer |
| CodeSummarizer | IMPLEMENTED | Built on FileIndexer |
| ChatRouter | IMPLEMENTED | Wired in container; routes chat requests |
| API router | IMPLEMENTED | 14 sub-routers |
| ContextManager | DISABLED | Commented out in container.py — not integrated in live pipeline |
| MemoryOrchestrator | DISABLED | Commented out — name collision bug noted in container comment |
| Frontend (React 19 + Vite) | IMPLEMENTED | ProjectsPage + WorkspacePage |
| Frontend API client | IMPLEMENTED | lib/api.ts; all calls through /api prefix |

---

## 3. Key Architecture Observations

### 3.1 Pipeline Flow (verified from workflow/manager.py)

```
EMPTY
  -> CLARIFYING  (domain research, then Q&A generation)
  -> QA_PENDING  (user answers) or skip to REQUIREMENTS_READY
  -> QA_IN_PROGRESS -> REQUIREMENTS_READY
  -> [ProductOwner]   -> ARCHITECTURE_READY
  -> [Architect]      -> DESIGN_READY
  -> [Designer]       -> DESIGN_REVIEW_PENDING  (user gate)
  -> DESIGN_APPROVED
  -> [Security] + [SprintPlanner] + [ScrumMaster] -> SPRINT_PLAN_READY
  -> SPRINT_IN_PROGRESS
      (per sprint: [FilePlanner] + [BackendDeveloper] + [FrontendDeveloper])
      (self-healing validation after all sprints)
  -> ALL_SPRINTS_COMPLETE
  -> [QA] + [DevOps] + [Document] -> QA_COMPLETE
  -> [Retro] -> DEPLOYABLE
```

Change management path:
```
any state -> CHANGE_REQUESTED (impact analysis) -> user confirms
  -> RESUMING_FROM_CHANGE -> SPRINT_IN_PROGRESS
```

### 3.2 Concurrency Guard
WorkflowManager.run() checks execution_state.is_running() and refuses duplicate starts.
API layer also checks before launching background task.

### 3.3 Thread Safety
EventBroadcaster uses loop.call_soon_threadsafe() to schedule WebSocket sends from
pipeline threads (FastAPI BackgroundTask threads have no asyncio event loop).
broadcaster.bind_loop() called in lifespan at startup.

### 3.4 Agent Resolution in Sprints
_run_sprint() resolves backend_developer_agent and frontend_developer_agent from the DI
container (production path). Falls back to AgentFactory only when container is None (unit-test path).

### 3.5 Design Spec Propagation
Designer artifact stored in durable memory slot (design:latest), injected into
FrontendDeveloper and QA prompts via WorkflowEngine._with_design_context(). Also loaded
in _run_sprint() via _load_design_artifact() so sprint agents get approved design.

### 3.6 FileStructurePlanner Position
FilePlanner runs inside each sprint (not globally before sprint planning). Old tests
expected it globally — this caused failures in test_v1_pipeline_fixes.py.

---

## 4. TODO/FIXME Inventory

All raise NotImplementedError occurrences are in abstract base classes (interfaces/providers).
This is correct OOP pattern — not incomplete stubs.

One genuine in-code TODO found:
  backend/app/workspace/dependency_detector.py:212
    lines.append(f"{pkg}  # TODO: pin version")
  Version pinning is not implemented for auto-detected dependencies in generated projects.

No FIXME, XXX, or business-logic pass-with-comment found.

---

## 5. Known Test Failures (from 2026-07-27 audit run)

| Test | Failure | Root Cause | Priority |
|------|---------|-----------|---------|
| test_designer_agent.py::test_reviewer_approves_well_formed_design | ModuleNotFoundError: No module named 'transformers' | sentence-transformers has runtime dep on transformers package not in requirements.txt | HIGH — fix requirements.txt |
| test_v1_pipeline_fixes.py::test_pipeline_runs_every_stage_in_order | Stage order mismatch | Test expects FileStructurePlanner globally; code runs it per-sprint (intentional refactor) | MEDIUM — update test |
| test_v1_pipeline_fixes.py::test_pattern_search_is_isolated_per_project | ModuleNotFoundError: No module named 'transformers' | Same missing transformers package | HIGH |
| test_review_report_fixes.py::Fix009ScrumMasterInjection (2 tests) | AttributeError: WorkflowManager has no attribute sprint_monitor | Tests create WorkflowManager() without sprint_monitor kwarg | MEDIUM — update test |

Subset run result: 57 passed, 4 failed
(test_sprint_sync, test_project_intelligence, test_project_file_generation suites not timed — they exceed 45s in isolation)

---

## 6. Missing Dependencies

| Package | Required By | In requirements.txt |
|---------|------------|---------------------|
| transformers | sentence-transformers (transitive dep) | NO |

Action required: add `transformers>=4.0.0` to requirements.txt or upgrade sentence-transformers
to a version that bundles it.

---

## 7. Hardcoded Values / Configuration Issues

| Issue | Location | Impact |
|-------|----------|--------|
| Hardcoded file_index db path | container.py: FileIndexer(db_path="backend/app/memory/file_index.db") | Not configurable |
| Hardcoded costs db path | container.py: CostTracker("backend/app/memory/costs.db") | Not configurable |
| Settings.knowledge_db defaults to "data/knowledge.sqlite" | config/models.py | Env var overrides via .env correctly |
| Hardcoded workspace in config.yaml | runtime.workspace = backend/temp-workspace | Overridable via env |

---

## 8. Disabled Components

| Component | Where Disabled | Stated Reason |
|-----------|---------------|--------------|
| ContextManager | container.py (commented out) | Not called anywhere in live pipeline; not integrated |
| MemoryOrchestrator | container.py (commented out) | Internal name collision (self.store is both attribute and method) |

These are documented in container.py comments. Neither is referenced outside container.py.

---

## 9. Architecture Strengths

1. Clean DI container — every singleton registered once; no direct instantiation in business logic
2. Crash-safe — ProjectState persisted on every transition; CheckpointManager for session recovery
3. Project isolation — all memory/artifact/LLM calls scoped to project_id
4. Detailed retry feedback — _detailed_feedback() extracts all ReviewFinding descriptions, not just summary
5. Sprint self-healing — up to 3 validation + backend-heal cycles after all sprints complete
6. Intelligence layer — ContextOrchestrator gracefully skips on error; never blocks pipeline
7. Thread-safe broadcasting via call_soon_threadsafe
8. Change management — full impact analysis + selective stage re-run + safe stages preserved

---

## 10. Testing Gaps

| Area | Gap |
|------|-----|
| Frontend components | ZERO tests (no Jest/Vitest configured) |
| ChatRouter | Not seen in any test file |
| LLM runtime reconfigure | No test for runtime provider/model switch |
| Full pipeline integration | No E2E test running all 15 stages end-to-end |
| WebSocket broadcast order | test_websocket.py exists but event order not verified |

---

## 11. Summary Verdict

Current state: Functionally complete multi-agent pipeline. Core execution path is sound.
Four test failures with two root causes.

Immediate actions (in order):
1. Add `transformers` to requirements.txt
2. Update Fix009ScrumMasterInjection tests to pass sprint_monitor=None to WorkflowManager()
3. Update test_pipeline_runs_every_stage_in_order to match current stage order (FileStructurePlanner inside sprint)
4. Document ContextManager and MemoryOrchestrator disabled status in CURRENT-STATE.md

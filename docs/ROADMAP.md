# Implementation Roadmap

**Last Updated**: 2026-07-27
**Current Version**: 1.1
**Test Count**: 377 collected / ~57 passing in subset run / 4 known failures

---

## COMPLETED

### Core Pipeline (verified from source)
- 15-stage pipeline fully wired (DomainResearch through Retro)
- All 15 agents implemented and registered in AgentFactory
- WorkflowManager state machine (24 states; crash-safe)
- Three-tier review system (AUTO_FIX/ASK_HUMAN/FLAG) with detailed feedback injection
- Real code generation — BackendDeveloper and FrontendDeveloper write files to disk
- Crash-safe resume via ProjectState persistence + CheckpointManager
- Learning loop: trajectory recording + semantic pattern retrieval (per project_id)
- Knowledge embedding + HNSW semantic search (KnowledgeMemory)
- Lesson store: human-readable approved-pattern lessons per stage
- LLM provider abstraction: OllamaProvider (600s timeout) + BedrockProvider
- Runtime LLM switching via POST /settings/llm (no restart)
- Project isolation: all memory/artifacts scoped to project_id
- File validation + safety policy (Python/JS syntax; no path traversal)
- API layer: 14 sub-routers
- WebSocket real-time events (multi-tab; thread-safe broadcaster)
- DI container: 40+ singletons, hand-wired (kernel/container.py)
- Intelligence layer: FileIndexer + DependencyGraph + CodeSummarizer + ContextOrchestrator
- SprintMonitor: cross-sprint context + sprint output validation
- ImpactAnalyzer: stage-level + file-level requirement change impact
- Domain research agent (DomainResearcherAgent) before Q&A
- Interactive Q&A gate (ClarificationAgent: generate questions, process answers)
- Design review gate (user approves or requests revision)
- Self-healing validation (up to 3 heal cycles post-sprint)
- Sprint-level retry (up to 2 full sprint attempts on failure)
- Change management: CHANGE_REQUESTED -> RESUMING_FROM_CHANGE path
- CostTracker: per-call token/latency tracking
- Frontend: React 19 + Vite 8 + TypeScript 6 + Tailwind v4
- Frontend: ProjectsPage (dashboard) + WorkspacePage (pipeline, chat, files, logs, artifacts, metrics)

### Tests (verified from pytest collection)
- 377 tests across 47 files
- test_sprint_sync.py: 45 tests for sprint sync / SprintMonitor / ImpactAnalyzer
- test_project_intelligence.py: 46 tests for intelligence layer
- test_v1_pipeline_fixes.py: 20 tests (2 stale — see below)
- test_review_report_fixes.py: 29 tests (2 stale — see below)

---

## IN PROGRESS / KNOWN ISSUES

### Test Failures (4 tests, 2 root causes)

- **MISSING: `transformers` in requirements.txt**
  Affects: test_designer_agent, test_v1_pipeline_fixes (pattern isolation test)
  Fix: Add `transformers>=4.0.0` to requirements.txt
  Effort: 5 minutes

- **STALE: Fix009ScrumMasterInjection (2 tests)**
  Affects: test_review_report_fixes.py
  Fix: Update test to create WorkflowManager correctly with sprint_monitor kwarg
  Effort: 30 minutes

- **STALE: test_pipeline_runs_every_stage_in_order**
  Affects: test_v1_pipeline_fixes.py
  Fix: Update expected stage list — FileStructurePlanner now runs inside sprint, not globally
  Effort: 30 minutes

### Disabled Components
- **ContextManager** — not integrated in live pipeline (commented out in container.py)
- **MemoryOrchestrator** — name collision bug (self.store attribute/method conflict); disabled

---

## NEXT (Immediate — pre-next-dev-session)

Priority 1: Fix test suite
1. Add `transformers` to requirements.txt — 5 min
2. Fix Fix009ScrumMasterInjection tests — 30 min
3. Fix test_pipeline_runs_every_stage_in_order — 30 min
4. Run full pytest and confirm zero failures

Priority 2: Fix MemoryOrchestrator and re-enable
1. Rename conflicting attribute in MemoryOrchestrator — 1-2 hours
2. Re-wire in container.py
3. Add test coverage

Priority 3: Hardcoded paths
1. Add file_index_db + costs_db to Settings model (config/models.py)
2. Read from settings in container.py build()
3. Update .env.example

Priority 4: Write frontend tests
1. Set up Vitest + React Testing Library
2. Test ProjectsPage: project list render, new project modal
3. Test WorkspacePage: pipeline state rendering, stage rail

---

## FUTURE (from docs/future/)

### Phase 1 — Verified Output (docs/future/PHASE-1-verified-output.md)
- Sandbox execution: run generated code in a container, capture test results
- Feedback loop: inject test failures back into BackendDeveloper for targeted fixes
- Verifiable acceptance criteria per stage

### Phase 2 — Human-in-the-Loop (docs/future/PHASE-2-human-in-the-loop.md)
- Additional human review gates beyond Design and Q&A
- AWAITING_HUMAN_APPROVAL state (enum value exists, not yet wired)
- Inline code editing by user before pipeline continues

### Phase 3 — Deployment Packaging (docs/future/PHASE-3-deployment-packaging.md)
- Docker Compose generation for generated projects
- One-click deploy to Fly.io / Railway / Render
- CI/CD pipeline template generation

### Phase 4 — Analytics (docs/future/PHASE-4-analytics.md)
- Per-project cost dashboard (CostTracker data already collected)
- Stage success rate analytics (trajectory data already collected)
- Prompt quality scoring (PromptQualityAnalyzer implemented; not yet surfaced in UI)

### Phase 5 — Multi-User Auth (docs/future/PHASE-5-multi-user-auth.md)
- JWT-based authentication
- Project ownership + RBAC
- API rate limiting
- Multi-tenant workspace isolation

### Long-term
- Async pipeline execution (parallel stages where dependency graph permits)
- PostgreSQL backend (replace SQLite for multi-instance deployment)
- Redis for WebSocket scaling
- Additional LLM providers (OpenAI, Gemini, Mistral)
- Horizontal scaling validation

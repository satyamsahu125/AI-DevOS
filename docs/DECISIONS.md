# Architectural Decision Records — AI DevOS

**Format**: ADR (Architecture Decision Record)
**Last Updated**: 2026-07-27
**Evidence basis**: Actual source code inspection; decisions inferred from implementation choices

---

## ADR-001: Synchronous Pipeline (No asyncio in Execution Path)

**Date**: Before 2026-07-18 (original design)
**Status**: ACCEPTED

**Context**:
Each pipeline stage makes one or more LLM calls that can take 40-240 seconds (observed on
local 7B model). Stages depend sequentially on each other's output.

**Decision**:
The entire pipeline execution path (WorkflowManager -> WorkflowEngine -> ExecutionManager ->
Agent -> LLMProvider) is fully synchronous. No asyncio in the pipeline path.

**Evidence**:
- All manager/engine methods are plain def (not async def)
- OllamaProvider uses urllib.request (stdlib, synchronous)
- WorkflowManager.run() is called from FastAPI BackgroundTasks which runs in a threadpool

**Consequences**:
- Simple, debuggable, no coroutine lifecycle issues
- Cannot run multiple stages in parallel even when dependency graph permits
- One LLM call blocks the background thread for its full duration

**Trade-off accepted**: simplicity over throughput. Parallelism deferred to Phase 5+ roadmap.

---

## ADR-002: Hand-Wired DI Container (Not a Framework)

**Date**: Before 2026-07-19
**Status**: ACCEPTED

**Context**:
The system has 40+ singleton services. Options: use a DI framework (inject, dependency-injector),
or hand-wire.

**Decision**:
Implement a minimal DependencyContainer (core/dependency_container.py) with register_singleton/
resolve semantics, and wire all services in Container.build() (kernel/container.py).

**Evidence**:
- kernel/container.py: ~300 lines of explicit singleton registrations
- No third-party DI framework in requirements.txt

**Consequences**:
- Explicit wiring is easy to trace and debug
- No magic/reflection — what you read is what runs
- Build() must be maintained when adding new services
- No circular dependency detection (handled manually)

---

## ADR-003: Project Isolation via project_id Namespacing

**Date**: Before 2026-07-20
**Status**: ACCEPTED

**Context**:
Multiple projects can run concurrently (in theory). Memory, artifacts, and LLM call attribution
must not leak between projects.

**Decision**:
Every memory store, artifact store, trajectory record, lesson, and LLM cost record is
namespaced by project_id. Memory loads/stores always take project_id as first argument.

**Evidence**:
- MemoryManager.store(project_id, key, value) — project_id is first arg
- LearningLoop.get_relevant_patterns(..., project_id=project_id) — scoped search
- LessonStore.get_lessons(stage=..., project_id=...) — per-project lessons
- Broadcaster.stage_started(project_id, ...) — per-project WebSocket

**Consequences**:
- Two projects sharing the same stage name never see each other's patterns or lessons
- Cross-project pattern sharing must be implemented explicitly (not yet done)

---

## ADR-004: Three-Tier Reviewer (AUTO_FIX / ASK_HUMAN / FLAG)

**Date**: Before 2026-07-21
**Status**: ACCEPTED

**Context**:
LLM outputs vary in quality. A simple "is it non-empty" check was insufficient. Options:
use human review for every stage, or automate quality gates with defined tiers.

**Decision**:
Reviewer applies three tiers:
- AUTO_FIX: issue can be fixed programmatically (missing JSON field, wrong type)
- ASK_HUMAN: issue requires human judgment (failed acceptance criteria)
- FLAG: minor issue logged but artifact accepted

**Evidence**:
- review/reviewer.py: Reviewer class with tier-based ReviewFinding
- WorkflowEngine._detailed_feedback(): extracts all FindingDescriptions + suggestions for retry prompt

**Consequences**:
- Stages retry with specific, actionable feedback (not blind retry)
- Rejection rate is meaningful signal (logged via LearningLoop)
- Human-in-the-loop gate exists but currently only at Q&A and Design Review stages

---

## ADR-005: FileStructurePlanner Runs Per-Sprint

**Date**: 2026-07-24 (refactored from global pre-sprint position)
**Status**: ACCEPTED

**Context**:
Originally FileStructurePlanner ran once globally before any sprints started. This meant it
had no sprint-specific context (goal, features, tasks for this sprint) and its output was
overwritten on the first sprint anyway.

**Decision**:
FileStructurePlanner runs as the first step inside each sprint iteration (_run_sprint()),
giving it access to the sprint goal, features, and ScrumMaster task breakdown.

**Evidence**:
- WorkflowManager._run_sprint(): calls _run_stage(project_id, "file_planner", plan_context)
- WorkflowManager.DESIGN_APPROVED state: no longer calls FileStructurePlanner globally
- test_v1_pipeline_fixes.py::test_pipeline_runs_every_stage_in_order: now stale (TASK-003)

**Consequences**:
- Better file plans per sprint (context-aware)
- One LLM call per sprint for file planning (vs. one global call)
- Old tests testing global stage order need updating

---

## ADR-006: Sprint-Level + Stage-Level Retry

**Date**: Before 2026-07-24
**Status**: ACCEPTED

**Context**:
LLM calls can fail transiently (timeout, bad JSON, content rejection). Options: retry at stage
level only, or also at sprint level.

**Decision**:
Two independent retry layers:
1. **Stage-level retry** (WorkflowEngine): RetryPolicy.max_retries (default 3). Each retry
   injects reviewer feedback into prompt. Controlled by RetryPolicy.
2. **Sprint-level retry** (WorkflowManager._run_sprint_with_retry): max 2 full sprint attempts.
   Handles transient errors unlikely to repeat on a second attempt.

**Evidence**:
- WorkflowEngine.run(): `while self.retry_policy.should_retry(attempt):`
- WorkflowManager._run_sprint_with_retry(max_attempts=2)

**Consequences**:
- More resilient to transient failures
- Up to 6 LLM calls per stage in worst case (3 stage retries × 2 sprint retries)
- Long tail latency is bounded by retry limits

---

## ADR-007: Design Spec Preserved in Durable Memory Slot

**Date**: Before 2026-07-24
**Status**: ACCEPTED

**Context**:
The Designer stage output (design spec) must be available to FrontendDeveloper and QA,
which run many stages later. The predecessor message slot is single-slot (overwritten each stage).

**Decision**:
Designer's approved artifact is stored in a durable memory slot (`design:latest`) separate
from the predecessor message. WorkflowEngine._with_design_context() injects it into
FrontendDeveloper, QA, and FileStructurePlanner prompts specifically.
WorkflowManager._load_design_artifact() also loads it for sprint agents.

**Evidence**:
- workflow/engine.py: _DESIGN_MEMORY_KEY = "design:latest"
- workflow/engine.py: _DESIGN_DEPENDENT_STAGES = (FrontendDeveloper, QA, FileStructurePlanner)
- workflow/manager.py: _load_design_artifact() checks approved design -> memory slot -> raw artifact

**Consequences**:
- FrontendDeveloper always has the approved design spec
- Design spec survives any number of intervening stages
- Memory slot is project-scoped (concurrent projects never share designs)

---

## ADR-008: ContextManager Disabled (Not Integrated)

**Date**: 2026-07-24 (disabled)
**Status**: DEFERRED

**Context**:
ContextManager (app/context/context.py) was designed to centralize context building for agents.
WorkflowEngine already builds context via _with_predecessor_message, _with_relevant_patterns,
_with_design_context, _with_lessons, _with_intelligence_context. ContextManager was never called
in the live pipeline.

**Decision**:
Disabled in container.py with comment: "not called anywhere in the live pipeline and has no
integration point."

**Evidence**: container.py comment (lines referencing context_manager)

**Consequences**:
- ContextManager remains implemented but dead code
- Decision: either integrate it by replacing the 5 separate _with_* methods, or remove it
- See TASK-008 for resolution tracking

---

## ADR-009: EventBroadcaster Loop Binding at Startup

**Date**: 2026-07-22 (FIX-B)
**Status**: ACCEPTED

**Context**:
FastAPI BackgroundTask threads (where the pipeline runs) have no asyncio event loop.
asyncio.get_running_loop() raises RuntimeError in those threads. WebSocket sends (async
coroutines) cannot be scheduled from sync threads without explicit loop reference.

**Decision**:
broadcaster.bind_loop(asyncio.get_running_loop()) called in FastAPI lifespan at startup.
Broadcaster stores the loop reference and uses loop.call_soon_threadsafe() for all sends.

**Evidence**:
- app/main.py lifespan: `broadcaster.bind_loop(asyncio.get_running_loop())`
- events/broadcaster.py: `loop.call_soon_threadsafe(lambda: asyncio.ensure_future(...))`

**Consequences**:
- Thread-safe WebSocket sends from pipeline background threads
- Single event loop assumption (fine for single-worker uvicorn)
- Multi-worker deployment would require different approach (e.g., Redis pubsub)

---

## ADR-010: Ollama 600s Timeout

**Date**: Before 2026-07-24
**Status**: ACCEPTED

**Context**:
Default HTTP timeouts (30s) caused real stage call timeouts. Designer stage measured ~118s
for a nested JSON schema. FrontendDeveloper measured 240s+ for code generation with large context.

**Decision**:
OllamaProvider timeout set to 600s (10 minutes). Comment in ollama_provider.py documents
the measurement basis.

**Evidence**:
- llm/providers/ollama_provider.py: `def __init__(self, ..., timeout: int = 600)`
- Docstring: "FrontendDeveloper measured two consecutive real timeouts at 240s before this was raised"

**Consequences**:
- Stages will not timeout for any realistic local model run
- A hung Ollama call blocks the pipeline thread for up to 600s
- No cancel/interrupt mechanism for long-running LLM calls

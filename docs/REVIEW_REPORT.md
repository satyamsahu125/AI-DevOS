# AI DevOS — Complete Review Report
**Date:** 2026-07-26  
**Reviewer:** Senior Architect (Manual Code Review — No Test Execution)

---

## Executive Summary

AI DevOS is a multi-agent, Agile-based software generation platform. The core pipeline is **real and largely functional** — not a prototype. LLM calls, file writes, artifact persistence, reviewer gates, and memory layers are all wired to real implementations. However there are **critical bugs, architectural violations, dead code, and Agile flow gaps** that will cause silent failures on a real large project. These are documented below by severity.

---

## 1. Memory Systems — Types, Roles, and Status

The project uses **five distinct memory layers**. Each has a different purpose, persistence model, and lifecycle. All five are real implementations, not stubs.

### 1.1 MemoryManager (`memory/manager.py`) — Runtime Key-Value Store
**Type:** Persistent key-value, project-scoped  
**Backend:** SQLite (`memory.db`)  
**Role:** Single-slot inbox per project. Stores two critical keys: `workflow:latest_message` (the last stage's structured output, passed to the next stage as context) and `design:latest` (the approved Designer artifact, injected into FrontendDeveloper and QA). Also handles legacy `.txt` migration on first run.  
**Status:** Real. Working. Correctly namespaced by `project_id` (key = `{project_id}:{key}`), preventing cross-project contamination.  
**Why important:** Without this, every stage runs blind — it has no knowledge of what the previous stage produced.

### 1.2 KnowledgeMemory (`memory/knowledge_memory.py`) — Semantic Vector Store
**Type:** Persistent vector search  
**Backend:** SQLite (text/metadata) + HNSW index file (`knowledge.hnsw`, via `hnswlib`) + `sentence-transformers/all-MiniLM-L6-v2` embeddings (384-dim)  
**Role:** Stores approved agent trajectories as 384-dim embeddings. Searched by LearningLoop to find semantically similar past successful outputs before a stage runs.  
**Status:** Real. Full HNSW cosine similarity search, lazy model loading (shared singleton), index resizing, soft-delete support. Not a stub at all.  
**Why important:** This is the "learn from past runs" layer. Without it, every run starts cold.

### 1.3 LearningLoop (`memory/learning_loop.py`) — Trajectory Logger + Pattern Retrieval
**Type:** Persistent trajectory log + semantic retrieval  
**Backend:** SQLite (`learning.db`) + KnowledgeMemory  
**Role:** Records every stage attempt (approved or rejected) to SQLite. Only approved ones are embedded into KnowledgeMemory. Exposes `get_relevant_patterns(task, stage, project_id)` — called by WorkflowEngine before every stage run, scoped to project_id to avoid cross-project pollution.  
**Status:** Real. Project isolation is correctly implemented.  
**Why important:** Prevents the same mistakes from repeating across retries. WorkflowEngine injects patterns into the prompt before each attempt.

### 1.4 LessonStore (`memory/lesson_store.py`) — Human-Readable Lesson Log
**Type:** Persistent lesson store  
**Backend:** SQLite (`lessons.db`)  
**Role:** After every stage approval, a `Lesson` (what worked, what failed, reviewer feedback, retry count) is extracted and saved. Designed for human readability and future audit — not for semantic search.  
**Status:** Real and complete. Prune, export, and per-project queries all implemented.  
**Why important:** Complements KnowledgeMemory. KnowledgeMemory answers "what's similar?"; LessonStore answers "what did we explicitly learn?". Neither is used to feed prompts back in currently (lessons are stored but never retrieved into prompts — see Bug #4).

### 1.5 MemoryOrchestrator (`memory/memory_manager.py`) — Composite In-Memory Layer
**Type:** In-memory cache + index + store coordination  
**Backend:** Wraps MemoryRepository (SQLite), MemoryStore (dict), MemoryCache (LRU OrderedDict), MemoryIndex (dict), MemorySynchronization (flag), MemoryStatistics  
**Role:** Full CRUD coordination layer with LRU caching (max 50 entries), write-through store, and synchronization tracking.  
**Status:** Real — but **never used in the live pipeline**. The Container builds it as `memory_orchestrator` but nothing in WorkflowEngine, WorkflowManager, or any agent uses it. MemoryManager (the simple key-value layer) is used directly everywhere instead.  
**Why important:** The MemoryOrchestrator exists, is built as a singleton, and has its own subsystems (MemoryIndex, MemorySynchronization, MemoryStatistics, MemoryCleanup) — but they are all dead weight in the live pipeline.

---

## 2. Agent Audit — Contribution, Wiring, Real vs Stub

All agents inherit from `BaseAgent`, which delegates to a `primary_action` (a `LLMAction` subclass). All primary actions make real LLM calls via `LLMManager → OllamaProvider → /api/generate`. None are stubs.

| Agent | Stage Enum | Registry Key | Action | Sprint Role | Status |
|---|---|---|---|---|---|
| StrategicReviewAgent | StrategicReview | strategic_review | WriteStrategicBriefAction | Pre-pipeline only | Real |
| ProductOwnerAgent | ProductOwner | product_owner | WriteRequirementsAction | Pre-sprint | Real |
| ArchitectAgent | Architect | architect | WriteArchitectureAction | Pre-sprint | Real |
| DesignerAgent | Designer | designer | WriteDesignAction | Pre-sprint | Real |
| SecurityAgent | Security | security | WriteSecurityReportAction | Pre-sprint | Real |
| SprintPlannerAgent | SprintPlanning | sprint_planner | PlanSprintsAction | Sprint planning | Real |
| ScrumMasterAgent | ScrumMaster | scrum_master | WriteScrumPlanAction | Sprint planning | Real |
| FilePlannerAgent / FileStructurePlannerAgent | FileStructurePlanner | file_planner | WriteFilePlanAction | Per-sprint | Real |
| BackendDeveloperAgent | BackendDeveloper | backend | WriteBackendCodeAction | Per-sprint (file-by-file) | Real |
| FrontendDeveloperAgent | FrontendDeveloper | frontend | WriteFrontendCodeAction | Per-sprint (file-by-file) | Real |
| QAAgent | QA | qa | WriteQAReportAction | Post-sprint | Real |
| DevOpsAgent | DevOps | devops | WriteDeploymentAction | Post-sprint | Real |
| DocumentAgent | Document | document | WriteDocumentationAction | Post-sprint | Real |
| RetroAgent | Retro | retro | WriteRetrospectiveAction | Post-pipeline | Real |
| ClarificationAgent | Clarification | clarification | ClarifyRequirementsAction + GenerateQuestionsAction + ProcessAnswersAction | Pre-pipeline | Real (two-phase) |

**Notable:** `ChatRouter` is NOT a pipeline agent — it's a conversational interface, registered in the container but routed separately through `/api/chat`. It reads artifacts and can trigger stages. This is correct.

---

## 3. Bugs and Errors Found

### BUG-001 — CRITICAL: Missing Import in `api/dependencies.py`
**File:** `backend/app/api/dependencies.py` line 40  
**Problem:** `get_artifact_manager()` returns `container.artifact_manager` typed as `ArtifactManager`, but `ArtifactManager` is never imported in this file. Every endpoint that calls `Depends(get_artifact_manager)` will crash with `NameError: name 'ArtifactManager' is not defined` at FastAPI dependency injection time.  
```python
# Line 40 — type annotation references ArtifactManager which is not imported
def get_artifact_manager(container: Container = Depends(get_container)) -> ArtifactManager:
    return container.artifact_manager
```
**Fix:** Add `from ..artifact.manager import ArtifactManager` to the imports.

### BUG-002 — CRITICAL: `ExecutionEngine` in `execution/execution_engine.py` is a Ghost Class
**File:** `backend/app/execution/execution_engine.py`  
**Problem:** There are TWO classes named `ExecutionEngine` — one in `execution/execution_engine.py` (the old one, which has `execute(stage_name, content)` with no `project_id`) and one in `execution/engine.py` (the real one, which has `execute(project_id, stage_name, content, attempt)`). `ExecutionManager` imports from `execution/engine.py` (correct). But `execution/execution_engine.py` also imports `ExecutionResult` from **both** `shared/dto/execution_result.py` and `execution/execution_result.py` — and the latter shadows the former:
```python
from ..shared.dto.execution_result import ExecutionResult        # import #1
from .execution_result import ExecutionResult as DocumentedExecutionResult  # import #2 in engine.py
```
`execution/execution_engine.py` has a `status()` method that conflicts with the `status` attribute:
```python
self.status = ExecutionStatus.Idle  # attribute
def status(self) -> ExecutionStatus:  # method with same name — Python will shadow the attribute
    return self.status
```
This will raise `TypeError` if `status()` is ever called — the method overwrites the attribute on the instance. **`execution_engine.py` is dead code** (nothing imports it in the live path), but it will cause import-time confusion.

### BUG-003 — HIGH: `WorkflowTransition.transition()` is a No-Op
**File:** `backend/app/workflow/transition.py`  
**Problem:** The `WorkflowTransition` class simply returns the state it was given — it performs no actual state validation or transition logic:
```python
def transition(self, state: WorkflowState) -> WorkflowState:
    return state
```
WorkflowEngine calls `self.transition.transition(WorkflowState.Approved)` and `self.transition.transition(WorkflowState.Failed)`. Since the return value is just the input, this is pure dead code. The actual state tracking is done correctly in `WorkflowStateMachine` — but `WorkflowTransition` adds cognitive noise and suggests transitions are validated when they are not.

### BUG-004 — HIGH: `WorkflowDependency` is Never Used / Always Returns True
**File:** `backend/app/workflow/dependency.py`  
**Problem:** `WorkflowDependency("ProductOwner")` is instantiated in `WorkflowEngine.__init__` and stored as `self.dependency` — but `self.dependency` is never referenced anywhere in `WorkflowEngine.run()` or any other method. Its `validate()` always returns `True` unconditionally. The prerequisite check for "does ProductOwner run before Architect?" is **never enforced** at the engine level — it's enforced only at the WorkflowManager state machine level (which is correct), but the presence of this object implies it guards something it doesn't.

### BUG-005 — HIGH: LessonStore Lessons Are Written But Never Read Into Prompts
**File:** `backend/app/memory/lesson_store.py`, `workflow/engine.py`  
**Problem:** `WorkflowEngine._record_lesson()` saves a Lesson after every approval. But `get_lessons()` is never called anywhere in the pipeline. The lessons are stored and never fed back into prompts. This means the "explicit learning" layer has zero effect on future runs. Only the vector-based `LearningLoop.get_relevant_patterns()` is called (which uses KnowledgeMemory). The LessonStore is write-only in the live pipeline.

### BUG-006 — HIGH: `_run_sprint` Calls `self._get_agent("backend").execute_sprint()` But `AgentFactory.create()` Returns a New Instance Every Time With No LLM Context
**File:** `backend/app/workflow/manager.py` line 584  
**Problem:** `self._get_agent("backend")` calls `self._agent_factory.create("backend")` which calls `AgentFactory.create("backend")` which does `return implementation()` — no constructor arguments. So the BackendDeveloperAgent and FrontendDeveloperAgent created here have default `LLMManager()` instances, not the shared singleton from the Container. This means: (a) cost tracking is not attributed to the project, (b) `llm_manager.set_context()` was never called on these instances, and (c) configuration overrides won't apply. The Container registers `backend_developer_agent` and `frontend_developer_agent` as singletons with proper injection, but `_get_agent()` bypasses the container entirely.

### BUG-007 — MEDIUM: `WorkflowManager.run()` Has No Return on All Code Paths
**File:** `backend/app/workflow/manager.py` line 96  
**Problem:** The `while True` loop handles every `ProjectState` case, but for `RESUMING_FROM_CHANGE`, after transitioning to `SPRINT_IN_PROGRESS`, it `continue`s the loop — but no explicit `return` exists for that transition, and the loop will continue executing. If `CHANGE_REQUESTED` state is ever hit (it never appears in the `while True` body), the loop falls through with no `return` and Python returns `None`, crashing the caller that expects a `PipelineResult`. **There is no `elif state == ProjectState.CHANGE_REQUESTED` branch in the `while True`**, meaning a pipeline in `CHANGE_REQUESTED` state will loop forever until it hits an unknown state.

### BUG-008 — MEDIUM: `_run_validation_with_healing` Validates BEFORE the First Real Check
**File:** `backend/app/workflow/manager.py` line 652-683  
**Problem:** The method calls `self.project_validator.validate(project_id)` TWICE on the first iteration — once before the loop and once at the start of the loop body. The pre-loop call result is discarded:
```python
result = self.project_validator.validate(project_id)  # result thrown away
for attempt in range(1, max_healing_attempts + 1):
    result = self.project_validator.validate(project_id)  # called again immediately
```
This doubles validation cost on the first pass.

### BUG-009 — MEDIUM: `DependencyGraph.has_dependency()` Is Hardcoded and Wrong
**File:** `backend/app/workflow/dependency_graph.py` line 51  
**Problem:**
```python
def has_dependency(self, stage: str) -> bool:
    return stage.lower() == "product_owner"
```
This says only `product_owner` has dependencies — ignoring the entire `STAGE_DEPENDENCIES` dict defined in the same class. This method is incorrect relative to the data it sits next to. It's not used in the live pipeline (nothing calls it) but it signals the class was half-maintained.

### BUG-010 — MEDIUM: `WorkflowEngine.__init__` References `Any` Without Import
**File:** `backend/app/workflow/engine.py` line 94  
**Problem:** The `broadcaster` parameter is typed as `Any | None` but `Any` from `typing` is not imported in the file. The `from __future__ import annotations` at the top defers annotation evaluation (so it won't fail at class definition time), but any runtime inspection or Pydantic validation of this type would fail. This is a latent import error.

### BUG-011 — MEDIUM: `Container.resolve()` Uses `Any` Without Import
**File:** `backend/app/kernel/container.py` line 266  
**Problem:** `def resolve(self, service_name: str | None = None) -> Any:` — `Any` is not imported. Same deferred annotation issue as BUG-010.

### BUG-012 — LOW: `count_all_trajectories()` Docstring Is Factually Wrong
**File:** `backend/app/memory/learning_loop.py` lines 199-208  
**Problem:** The docstring says "The trajectories table has no project_id column" — but lines 93-95 of the same file add the column if it's missing, and it IS in the CREATE TABLE statement from line 78. The docstring was not updated after the project_id column was added.

### BUG-013 — LOW: Sprint Result Flow Ignores `SprintResult.message` on Failure
**File:** `backend/app/workflow/manager.py` line 306  
**Problem:**  
```python
elif result.sprint_complete:
    pass  # ← explicit pass with no comment, no action
```
When `result.sprint_complete` is True but `result.all_sprints_complete` is False, the loop just continues — which is correct. But `pass` with no comment makes it look like a forgotten implementation.

---

## 4. Unused Code

### DEAD-001: `execution/execution_engine.py` — Entire File
The old `ExecutionEngine` in `execution/execution_engine.py` is never imported in the live path. `ExecutionManager` correctly imports from `execution/engine.py`. This file has a broken `status()` vs `status` attribute collision and confuses anyone reading the codebase.

### DEAD-002: `MemoryOrchestrator` and Its Subsystems
`MemoryOrchestrator`, `MemoryStore`, `MemoryIndex`, `MemoryCache`, `MemorySynchronization`, `MemoryStatistics`, `MemoryCleanup` — built in the container, never called by any agent, action, or manager in the live pipeline. The live pipeline only uses `MemoryManager` (simple key-value), `KnowledgeMemory` (vectors), `LearningLoop`, and `LessonStore`.

### DEAD-003: `WorkflowDependency`
Built in `WorkflowEngine.__init__`, stored as `self.dependency`, never referenced again.

### DEAD-004: `WorkflowTransition`
Built in `WorkflowEngine.__init__`, called twice, returns its input unchanged. No logic.

### DEAD-005: `AgentMetadata` (`agents/metadata.py`)
A 3-field dataclass. Nothing in the live pipeline reads or writes it.

### DEAD-006: `MemoryContext` (`memory/memory_context.py`)
A structured context container for prompt builders. Nothing in the live pipeline populates or reads it. The actual context injection is done by `WorkflowEngine._with_predecessor_message()` and `_with_design_context()` with raw strings, not this class.

### DEAD-007: `ContextManager` (`context/context.py`)
Registered in the Container, but never injected into WorkflowEngine or any agent. Context building happens inside WorkflowEngine directly.

### DEAD-008: `LessonStore.get_lessons()` — Never Called
Lessons are stored after every approval. `get_lessons()` and `get_all_lessons()` are never called in the live pipeline (see BUG-005).

### DEAD-009: `AgentInterface` (`shared/interfaces/agent_interface.py`)
Imported and stored as the `registry` list type in Container. The registry list holds managers, not agents — and nothing in the live path uses `AgentInterface`.

---

## 5. Workflow Engine — Complete Flow Check

### 5.1 Normal (Happy) Path

```
POST /workflow/start
  → background_tasks.add_task(manager.run, project_id, content)
  → WorkflowManager.run()
    → state=EMPTY → transition to CLARIFYING
    → state=CLARIFYING
        → ClarificationAgent.generate_questions()
        → if questions: save, transition QA_PENDING, return (wait for user)
        → else: run StrategicReview stage, transition REQUIREMENTS_READY
    → state=REQUIREMENTS_READY → run ProductOwner → ARCHITECTURE_READY
    → state=ARCHITECTURE_READY → run Architect → DESIGN_READY
    → state=DESIGN_READY → run Designer → DESIGN_REVIEW_PENDING (return, wait)
    → [User approves design via POST /workflow/{id}/design-review]
    → state=DESIGN_APPROVED
        → run Security
        → run SprintPlanner → save sprint plan to project.json
        → run ScrumMaster
        → run FileStructurePlanner
        → transition SPRINT_PLAN_READY
    → state=SPRINT_PLAN_READY → transition SPRINT_IN_PROGRESS
    → state=SPRINT_IN_PROGRESS
        → _run_next_sprint()
          → _run_sprint(sprint)
            → _run_stage("file_planner", sprint_context)  ← per-sprint file plan
            → _load_file_plan()
            → backend_agent.execute_sprint(file_plan)  ← file-by-file LLM calls
            → frontend_agent.execute_sprint(file_plan, design_artifact)
            → mark_sprint_complete()
          → repeat for all sprints
          → when all done: _run_validation_with_healing() → transition ALL_SPRINTS_COMPLETE
    → state=ALL_SPRINTS_COMPLETE
        → run QA
        → run DevOps
        → run Document
        → transition QA_COMPLETE
    → state=QA_COMPLETE → run Retro → transition DEPLOYABLE
    → return PipelineResult(success=True)
```

Every stage runs through `WorkflowEngine.run()` which enforces: execute → review → retry (max 3 attempts). On approval: records AgentMessage (for next stage), records trajectory (for LearningLoop), records lesson (for LessonStore), saves checkpoint cleanup, updates project.json.

### 5.2 Reviewer Gate (Real, Not Stub)

The Reviewer is real with three tiers:
- **AUTO_FIX**: empty content, missing design system keys, components with no states — logged but do not block.
- **ASK_HUMAN**: missing structured output for a schema, content < 10 chars, dead-end user flows, missing accessibility notes, missing page layouts, no user flows, skipped files in code stages — **BLOCK approval**.
- **FLAG**: low quality score (< 0.6), content > 8000 chars, repeated content from previous attempt — logged, do not block.

`approved = content_valid AND no ASK_HUMAN findings`. This is real quality gating.

### 5.3 Agile Flow Analysis

**What works:** Sprint plan is created by SprintPlannerAgent (LLM-generated, validated against `SprintPlanSchema`), saved to `project.json`. `_run_next_sprint()` reads the plan and executes sprints in order. Each sprint runs FileStructurePlanner (per-sprint), then BackendDeveloper and FrontendDeveloper file-by-file. Sprint completion is persisted. The design artifact is injected into frontend prompts.

**What is broken or missing:**

1. **Sprint-level failure does not halt the pipeline gracefully.** In `state=SPRINT_IN_PROGRESS`, when `_run_next_sprint()` returns a `SprintResult` with `sprint_complete=False` and `all_sprints_complete=False`, the code calls `return self._fail(project_id, "Sprint", result)`. But `SprintResult` and `WorkflowResult` have different fields — `SprintResult` has no `.message` attribute in the same schema as `WorkflowResult`. `self._fail()` calls `result.message` which may be `None` on `SprintResult` if the field wasn't set — leading to a `NoneType` in the failure message, not a crash, but misleading.

2. **`_get_agent("backend")` bypasses DI container** (BUG-006 above). Backend and Frontend agents called from `_run_sprint` have default `LLMManager` instances — not the shared, configured singleton. If the LLM is configured for Bedrock, these agents will use Ollama (the default).

3. **No retry at the sprint level.** If `execute_sprint()` fails for a file (after 3 internal per-file attempts), the entire sprint fails and the pipeline fails. There is no sprint-level retry in `WorkflowManager`. The per-stage retry (3 attempts in `WorkflowEngine`) does NOT apply to sprint execution — `execute_sprint()` is called directly, bypassing `WorkflowEngine.run()` entirely.

4. **ScrumMaster's output is unused.** `WriteScrumPlanAction` produces a `ScrumPlanSchema` artifact. The artifact is stored. But nothing in `_run_sprint()` reads or applies the ScrumMaster's output — the sprint context is built from the SprintPlan, not from the ScrumMaster's plan. The ScrumMaster runs, produces output, and its artifact sits unused.

5. **FileStructurePlanner runs twice for every sprint.** First, it runs globally in `state=DESIGN_APPROVED` via `self._run_stage(project_id, "FileStructurePlanner", request)`. Then it runs again per-sprint in `_run_sprint()` via `self._run_stage(project_id, "file_planner", plan_context)`. The global run's artifact is overwritten by the per-sprint run. This is confusing and wasteful.

---

## 6. Negative Scenario Analysis

### Scenario A: LLM Returns Empty Content
**Flow:** `OllamaProvider.execute()` returns `LLMResponse(content="")` → `LLMAction.run()` returns `ActionOutput(content="")` → `BaseAgent.execute()` returns `StageArtifact(content="")` → `Reviewer._check_auto_fix()` fires (`AUTO_FIX`), `_check_ask_human()` fires (content_valid=False triggers `content < 10 chars` check, actually not — the `content_valid=False` short-circuits ask_human's second check). Actually: `content_valid = bool("".strip()) = False` → `AUTO_FIX` finding added, `human_questions` is empty (the ask_human check for short content requires `content_valid=True`). Result: `approved = content_valid AND no human_questions = False AND True = False`. Correctly rejected. RetryPolicy allows retry. **Verdict: Handled correctly.**

### Scenario B: LLM Returns Valid Text But No JSON (Schema Required Stage)
**Flow:** Schema-stage agent (e.g., SprintPlanner) gets back prose instead of JSON. `BaseAction.extract_json()` tries 3 candidates, all fail, returns `{}`. `structured = {}`. `Reviewer._check_ask_human()`: `artifact.schema_type` is `"PlanSprints"` (non-empty), `artifact.structured_content` is `{}` (falsy) → **ASK_HUMAN fired**. `approved = False`. Retry with feedback injected. **Verdict: Handled correctly.**

### Scenario C: Reviewer Rejection Loop Exhaustion
**Flow:** `RetryPolicy(max_retries=3)`. `should_retry(attempt=0)` → True, `should_retry(1)` → True, `should_retry(2)` → True, `should_retry(3)` → False. Loop exits after 3 attempts. `WorkflowEngine.run()` sets state to `Failed`, deletes checkpoint, records `_update_project_failure()`, returns `WorkflowResult(success=False)`. `WorkflowManager._fail()` transitions to `ProjectState.FAILED`. **Verdict: Handled correctly.** However, once in `FAILED` state, calling `continue` re-enters the state machine, hits `state == ProjectState.FAILED`, and returns a `PipelineResult(success=False)` — no automatic re-run. User must call `/workflow/stage` to re-run a specific stage. **Verdict: Correct but not communicated to the user.**

### Scenario D: User Submits Duplicate `/workflow/start` While Pipeline is Running
**Flow:** `manager.execution_state.is_running(project_id)` returns True → API returns 200 with "Workflow is already running in background" without starting a second background task. **Verdict: Correctly guarded.** Note: the HTTP response is 200 not 409 — this may confuse API clients that expect an error status for "already running".

### Scenario E: Design Stage Approved, Then Sprint Fails, Then User Calls `/workflow/continue`
**Flow:** State is `FAILED`. `manager.run()` → hits `state == ProjectState.FAILED` → returns `PipelineResult(success=False, message="Pipeline in state: failed")`. The pipeline does NOT automatically restart from the last good state. The user must call `POST /workflow/{id}/change` or `POST /workflow/stage` explicitly. **Verdict: No automatic resume from failure — requires manual intervention. Not documented to the user in the API response.**

### Scenario F: SprintPlan is Missing (LLM Failed to Produce Valid JSON)
**Flow:** `WorkflowEngine.run()` for SprintPlanning stage: SprintPlannerAgent returns text, `BaseAction.extract_json()` fails → `structured_content = {}` → Reviewer fires ASK_HUMAN (missing structured output) → 3 retries, all fail → `WorkflowResult(success=False)`. In `WorkflowManager.run()` `state=DESIGN_APPROVED`: `result_sp = self._run_stage(project_id, "SprintPlanner", request)` → `not result_sp.success` → `return self._fail(project_id, "SprintPlanning", result_sp)`. `_run_next_sprint()` is never reached. **Verdict: Handled correctly.**

Then if `_run_next_sprint()` IS reached with an empty sprint plan anyway (shouldn't happen): `plan = self.workspace.get_sprint_plan(project_id)` → `not plan or not plan.sprints` → `_run_default_sprint()` → runs BackendDeveloper and FrontendDeveloper without a file plan or sprint context. This is a real fallback, not a stub, but it produces generic output with no sprint structure.

### Scenario G: Requirement Change Mid-Sprint
**Flow:** `POST /workflow/{id}/change` → `submit_requirement_change()` → `ImpactAnalyzer.analyze()` → determines affected stages → saves `pending_change`, transitions to `CHANGE_REQUESTED`. But `CHANGE_REQUESTED` is **never handled in the `while True` loop in `WorkflowManager.run()`**. The loop will keep cycling through the `while True` without matching any state and will loop forever (or until all states are exhausted), returning `None`. **This is an active bug** — confirmed by reading the loop: `EMPTY`, `CLARIFYING`, `QA_PENDING`, `QA_IN_PROGRESS`, `REQUIREMENTS_READY`, `ARCHITECTURE_READY`, `DESIGN_READY`, `DESIGN_REVIEW_PENDING`, `DESIGN_APPROVED`, `SPRINT_PLAN_READY`, `SPRINT_IN_PROGRESS`, `ALL_SPRINTS_COMPLETE`, `QA_COMPLETE`, `RESUMING_FROM_CHANGE`, then `DEPLOYABLE/DONE/FAILED/PAUSED`. `CHANGE_REQUESTED` is not in the list.

### Scenario H: Memory Manager Called with Empty project_id
**Flow:** `MemoryManager.store("", "workflow:latest_message", data)` → key = `":workflow:latest_message"`. Another project with `project_id=""` would load it. This could happen if `WorkflowEngine.run()` is called with an empty `project_id`. The engine does not validate `project_id` at entry. **Latent bug — no guard.**

---

## 7. Architecture Principle Violations

1. **Agents communicate via direct calls in `_run_sprint()`**, not only through artifacts and memory. `_get_agent("backend").execute_sprint()` and `_get_agent("frontend").execute_sprint()` are called directly from WorkflowManager, bypassing WorkflowEngine entirely. This violates "Workflow Engine is the only orchestrator."

2. **Agents not stateless in sprint path.** `BackendDeveloperAgent` and `FrontendDeveloperAgent` hold `project_writer`, `validator`, and `llm_manager` as instance state. When created via `AgentFactory.create()` (which does `implementation()` with no args), they get default instances — defeating DI. Stateless agents should receive all dependencies through the execution context, not through constructor injection that gets bypassed.

3. **WorkflowEngine does not own the sprint execution path.** The sprint loop runs in `WorkflowManager._run_sprint()` directly. This means retry policy, reviewer gating, checkpoint management, lesson recording, and trajectory recording do NOT apply to individual file generation — only to the high-level stage (FileStructurePlanner). Backend and frontend file generation have their own 3-attempt retry but no reviewer gating.

4. **Execution Engine has a dead twin.** Having both `execution/engine.py` and `execution/execution_engine.py` creates confusion about which is authoritative.

---

## 8. Summary Table

| ID | Severity | Category | Description |
|---|---|---|---|
| BUG-001 | CRITICAL | Import Error | `ArtifactManager` not imported in `api/dependencies.py` |
| BUG-002 | CRITICAL | Dead Class | `execution_engine.py` has `status` attribute vs method collision, is dead code |
| BUG-003 | HIGH | Logic | `WorkflowTransition.transition()` is a no-op |
| BUG-004 | HIGH | Dead Code | `WorkflowDependency` created but never used |
| BUG-005 | HIGH | Missing Wiring | `LessonStore.get_lessons()` never called — lessons are write-only |
| BUG-006 | HIGH | DI Bypass | `_get_agent()` bypasses container; Backend/Frontend get default `LLMManager` |
| BUG-007 | MEDIUM | Missing State | `CHANGE_REQUESTED` not handled in `WorkflowManager.run()` loop — infinite loop |
| BUG-008 | MEDIUM | Logic | Double validation on first healing attempt |
| BUG-009 | MEDIUM | Wrong Logic | `DependencyGraph.has_dependency()` hardcoded to return True only for `product_owner` |
| BUG-010 | MEDIUM | Import | `Any` not imported in `workflow/engine.py` (deferred annotation masks it) |
| BUG-011 | MEDIUM | Import | `Any` not imported in `kernel/container.py` |
| BUG-012 | LOW | Docs | `count_all_trajectories()` docstring says no `project_id` column — column exists |
| BUG-013 | LOW | Style | Explicit `pass` with no comment in sprint result handler |
| DEAD-001 | HIGH | Dead Code | `execution/execution_engine.py` entire file |
| DEAD-002 | MEDIUM | Dead Code | `MemoryOrchestrator` + subsystems built but unused |
| DEAD-003 | MEDIUM | Dead Code | `WorkflowDependency` |
| DEAD-004 | MEDIUM | Dead Code | `WorkflowTransition` |
| DEAD-005 | LOW | Dead Code | `AgentMetadata` |
| DEAD-006 | LOW | Dead Code | `MemoryContext` |
| DEAD-007 | LOW | Dead Code | `ContextManager` (registered, not injected) |
| DEAD-008 | MEDIUM | Dead Code | `LessonStore.get_lessons()` / retrieval path |
| DEAD-009 | LOW | Dead Code | `AgentInterface` |

---

## 9. What Is Working Correctly

- The full pipeline from EMPTY → DEPLOYABLE runs end-to-end with real LLM calls.
- Reviewer gating is real — three-tier, blocks on ASK_HUMAN, does not block on FLAG.
- Memory namespacing by project_id is correct — no cross-project contamination.
- KnowledgeMemory + HNSW vector search is real and correctly scoped.
- Checkpoint save/delete lifecycle is correct.
- Concurrent pipeline guard (duplicate-start protection) is correct.
- Stop request propagation is correct (thread-safe set, checked before each attempt).
- Design artifact injection into FrontendDeveloper is correct (both via WorkflowEngine and via `_load_design_artifact` in the sprint path).
- Requirement change flow (submit → analyze → confirm → re-run) is architecturally complete, except for the missing `CHANGE_REQUESTED` state handler (BUG-007).
- Per-file retry with validation feedback (BackendDeveloper, FrontendDeveloper) is real.
- Sprint plan persistence and resume are real.
- Self-healing validation after all sprints is real (runs BackendDeveloper with error context).

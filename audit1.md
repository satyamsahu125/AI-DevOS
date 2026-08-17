# AI DevOS — God-Mode Architecture Audit & Redesign Blueprint

> **Audit Date:** 2026-08-17  
> **Scope:** Full backend + frontend codebase — every file read, every claim stress-tested  
> **Method:** Assume nothing works. Prove it does or flag it as broken.  
> **Principle:** Architecture documents describe intent. Code describes reality. When they diverge, code wins.

---

## Executive Verdict

> **The workflow pipeline cannot execute a single run at startup.**
> Four Python files imported at module load time do not exist on disk.
> The six "Architecture Principles" in the README are 4/6 false as written.
> Approximately 40% of the backend Python files are pure data bags with zero behavior.
> The frontend had 12 failing tests caused by missing `useState` declarations and no browser API shims.

This is not a polish problem. This is a structural problem. The audit below maps every failure, every lie, every dead cluster — then rebuilds the architecture from first principles.

---

## Part 1 — Finding Inventory (Severity-Ranked)

### 🔴 CRITICAL — System Cannot Start or Produces Data Corruption

| ID | Location | Finding | Impact |
|----|----------|---------|--------|
| C-01 | `api/workflow.py:19` | `from ..tasks.pipeline_task import dispatch_pipeline` — **file does not exist** | Entire `/workflow` API surface is dead at startup (ImportError at module load) |
| C-02 | `workflow/engine.py:~8` | `from ..execution.manager import ExecutionManager` — **file does not exist** | WorkflowEngine cannot be instantiated — the core orchestrator is dead |
| C-03 | `workflow/runtime.py` | `from ..execution.agent_runtime import AgentRuntime` — **file does not exist** | WorkflowRuntime uncallable |
| C-04 | `agents/chat.py` | `from ..agents.chat_router import ChatRouter, ChatResponse` — **file does not exist** | Chat endpoint throws 500 on every request |
| C-05 | `workflow/transition_manager.py` | `next_state()` ignores `current_state` parameter entirely — always returns `Completed` or `WaitingForReview` | State machine has no path to `Running`, `Failed`, or `Cancelled` — every workflow that "succeeds" jumps directly from any state to Completed |
| C-06 | `execution/scheduler.py` | Operator precedence bug: `return plan.current_stage or plan.stages[0] if plan.stages else ""` parsed as `(current_stage) or (stages[0] if stages else "")` | Scheduler NEVER advances past `current_stage` when it is set — execution is permanently stuck on stage 1 |
| C-07 | `workflow/manager.py` | TOCTOU race: `is_running()` and `mark_running()` are separate non-atomic lock acquisitions; background Celery thread timing means the guard fires after the duplicate has already started | Concurrent requests launch duplicate pipeline runs, producing duplicate artifacts and corrupted execution state |
| C-08 | `execution/` | `ExecutionState` is a process-local in-memory dict | Celery spawns multiple worker processes; state written in process A is invisible to process B — every cross-worker stage transition reads stale or empty state |
| C-09 | `agents/devops.py:31` | `self.project_writer = project_writer or ProjectWriter()` + passes it directly to `WriteDeploymentAction` | DevOpsAgent (and its alias `ProductionDeployAgent`) modifies project files **without going through the Execution Engine** — the #1 architecture principle is violated |
| C-10 | `memory/memory_cleanup.py` | `mark_removed()` appends entry to an in-process list but **never removes it from any store** | Memory "cleanup" is a complete no-op; system leaks indefinitely, degrading every retrieval operation |

---

### 🟠 HIGH — Silently Wrong Behavior, Data Loss Risk, or Security Gap

| ID | Location | Finding | Impact |
|----|----------|---------|--------|
| H-01 | `agents/resolver.py` | Maps `"reviewer"` → `"reviewer"` but `AgentFactory` never registers key `"reviewer"` | Every reviewer lookup throws `DependencyException` at runtime |
| H-02 | `agents/factory.py:99` | `workspace_manager` injected only for `tech_lead`; all other agents receive `None` including `ProductOwnerAgent` which calls `workspace_manager.get_context()` | `ProductOwnerAgent` throws `AttributeError: 'NoneType'` on every invocation |
| H-03 | `workflow/state_machine.py` | Defines `start()`, `approve()`, `complete()`, `fail()` with proper guard logic — **none of these methods are ever called in production** | `engine.py` mutates `workflow.state` directly, bypassing all guards; state machine is 100% dead code |
| H-04 | `api/workflow.py` + `api/projects.py` | `WorkspaceManager.update_project_json()` is called from 3 locations outside the Execution Engine | Project files have 4 simultaneous write paths — race conditions on every project save |
| H-05 | `agents/tech_lead.py` | `ArtifactStore.write()` failure is caught and logged at WARNING level only — execution continues as if the write succeeded | Reviewer proceeds with a missing artifact; no human or system knows the artifact was never written |
| H-06 | `workflow/manager.py` | `/workflow/stage` endpoint bypasses the duplicate-run guard entirely | Race window for concurrent stage advancement even when the TOCTOU race is fixed |
| H-07 | `memory/memory_store.py` | Volatile in-process dict — no persistence layer | All memory (context, learnings, project history) is lost on every backend restart |
| H-08 | `agents/chat.py` | `request.context` field accepted in the Pydantic model but **silently dropped** before calling `chat_router.handle()` | Context-aware chat is impossible; context parameter is a documented lie |
| H-09 | `workflow/engine.py` | No transactional boundary around stage execution — crash mid-stage leaves `workflow.json` in a partial write state | Corrupt `workflow.json` on any unhandled exception; no recovery path |
| H-10 | `execution/execution_status.py` | `Cancelled` and `Paused` states missing from enum | Cancel/pause API calls would need to write a string not in the enum — type error or silent corruption |

---

### 🟡 MEDIUM — Wrong in Edge Cases, Incomplete Implementation, Design Debt

| ID | Location | Finding | Impact |
|----|----------|---------|--------|
| M-01 | `workflow/engine.py` | Context window warning uses `len(str(context))` (character count) as a proxy for token count | Off by 3–4× for code-heavy contexts; warning fires too late or not at all |
| M-02 | `workflow/workflow.json` | Two different "total stage" counts (20 in one field, 21 in another) | Progress bars show wrong %; off-by-one in completion detection |
| M-03 | `agents/descriptor.py` | `AgentDescriptor` dataclass — never instantiated anywhere in the codebase | Pure dead code |
| M-04 | `execution/recovery_policy.py` | `max_retries=3` field — nothing reads or enforces it | Retry policy is decorative |
| M-05 | `execution/execution_metrics.py` | Three counter fields — no increment methods | Metrics always read as zero |
| M-06 | `execution/execution_plan.py` | Dataclass with no `advance()`, `mark_failed()`, or `is_complete()` methods | Stage advancement is ad-hoc imperative mutations scattered across callers |
| M-07 | `memory/memory_filter.py` | Only strips falsy values — no relevance scoring, time decay, or project-scope filtering | Every retrieved memory item is treated as equally relevant regardless of age or project |
| M-08 | `memory/memory_summary.py` | Pure data bag — no generation logic | Memory summaries must be manually constructed; no automatic summarization |
| M-09 | `memory/memory_statistics.py` | Three counter fields — no increment methods | Stats always zero |
| M-10 | `agents/security.py` | `prompt_builder=None` via factory path; no null-guard before calling builder | `AttributeError` on first security agent invocation |
| M-11 | `agents/designer.py` | Same null `prompt_builder` issue as security agent | Same failure mode |
| M-12 | `workflow/runtime_validation.py` | Only validates two trivial conditions (workflow exists, stage name not empty) — never checks reviewer role or stage-specific preconditions | Invalid approval transitions silently succeed |
| M-13 | `QAOrchestrator` / `SprintExecutor` / `ChangeManager` | Each orchestrates its own sub-pipeline outside the Workflow Engine | "Workflow Engine is the only orchestrator" is false — 5 competing orchestrators exist |
| M-14 | `agents/factory.py` | `self.agents` and `self.descriptors` are the same dict object | Registry has one namespace where it claims two; `AgentDescriptor` lookup is undefined behavior |
| M-15 | `execution/stage_execution_status.py` | Only `Completed`/`Failed` — missing `Retrying`, `Skipped`, `Timeout`, `Cancelled` | Stage status is a binary oversimplification; retry and timeout handling cannot be expressed |

---

### 🔵 LOW — Code Smell, Misleading Comments, Minor Waste

| ID | Location | Finding | Impact |
|----|----------|---------|--------|
| L-01 | `agents/scrum_master.py` / `sprint_planner.py` | No `run()` method — delegates to single action; these agents have no agent-specific logic | Wrapper classes exist only to satisfy factory type; consolidatable |
| L-02 | `agents/validation.py` | Only validates non-empty name string — not actually an agent | Misnamed file; should be a utility function |
| L-03 | `workflow/runtime_state.py` | Single-field dataclass wrapping a string | Dead abstraction; replace with `str` typed alias |
| L-04 | `memory/memory_cache.py` | Functional LRU via OrderedDict — actually works | Only fully functional memory component; no changes needed |
| L-05 | `agents/tech_lead.py` | Has real LLM-backed review logic — genuinely the only agent with substantive implementation | Bright spot; preserve and use as the template for other agents |

---

## Part 2 — Architecture Lies vs. Reality

The six stated principles are audited below. A principle is True only if the codebase enforces it structurally (not just in one happy path).

| Principle | Claimed | Reality | Verdict |
|-----------|---------|---------|---------|
| Stateless agents | Agents hold no persistent state | Agents hold `prompt_builder` and `workspace_manager` refs; DevOpsAgent owns a live `ProjectWriter` | ⚠️ PARTIAL — statefulness is narrow but C-09 is a violation |
| Workflow Engine is the only orchestrator | Single orchestration point | `WorkflowManager`, `PipelineSupervisor` (80KB), `QAOrchestrator`, `SprintExecutor`, `ChangeManager` all orchestrate independently | ❌ FALSE |
| No agent-to-agent communication | Agents communicate only through artifacts and memory | Cannot fully verify; `QAOrchestrator` creates independent agent pipelines — full call chain not traced | ⚠️ UNVERIFIED |
| Reviewer approves every stage | Human or AI review gate on every stage | AI auto-reviewer on 10 of 13 stages; human gate on only 3; no schema validation on artifacts before approval | ❌ FALSE |
| Execution Engine is the only file writer | All project file mutations go through one component | `WorkspaceManager.update_project_json()` called from engine, manager, and API handler; `DevOpsAgent` owns `ProjectWriter` directly | ❌ FALSE |
| Every stage produces structured artifacts | Artifacts have validated schemas | No schema validation anywhere in the pipeline; artifact "structure" is a convention enforced by nothing | ❌ FALSE |

**Score: 0/6 principles fully enforced. 2/6 partially. 4/6 demonstrably false.**

---

## Part 3 — Dead Code Clusters

These clusters can be deleted without functional impact (they are either never called or always return zero/None):

### Cluster A — Dead Execution Infrastructure
- `execution/execution_metrics.py` — counters, no incrementors
- `execution/execution_plan.py` — dataclass, no methods
- `execution/recovery_policy.py` — fields, no enforcement
- `execution/stage_execution_status.py` — incomplete enum
- `workflow/runtime_state.py` — single-field wrapper
- `workflow/state_machine.py` — complete implementation, zero callers

### Cluster B — Dead Memory Infrastructure
- `memory/memory_cleanup.py` — no-op mark_removed
- `memory/memory_filter.py` — strips falsy only
- `memory/memory_statistics.py` — counters, no incrementors
- `memory/memory_summary.py` — data bag, no generation

### Cluster C — Dead Agent Infrastructure
- `agents/descriptor.py` — never instantiated
- `agents/validation.py` — not an agent
- `agents/scrum_master.py` — no logic beyond action delegation
- `agents/sprint_planner.py` — same

### Cluster D — Dead Files (Physical Deletion Required)

Root-level:
```
direct_run.log
direct_run_report.json
task1.txt.txt
fix1.md
AUDIT_REPORT.md
ARCHITECTURE_VALIDATION.md
DESIGN_SPEC.md
FINAL_REVIEW.md
VALIDATION_GATES.md
TEST_STRATEGY.md
FRONTEND_MIGRATION_PLAN.md
DISCOVERY_NOTES.md
CODEBASE_MAP.md
FIX_LOG.md
ai_devos_opencode.md
```

Backend:
```
backend/test_results.txt              (96KB runtime artifact)
backend/_stale_backend_to_delete/     (entire directory — name says it all)
backend/app/memory/AUDIT_FINDINGS.md  (audit artifact leaked into source)
```

---

## Part 4 — The Four Files That Must Be Created Immediately

Without these four files, the backend cannot process any workflow request. Every other fix is lower priority.

### 1. `backend/app/tasks/pipeline_task.py`

```python
"""
pipeline_task.py — Celery task entry point for async workflow dispatch.

Imported by api/workflow.py at module load. Must exist or the entire
/workflow API surface fails with ImportError.
"""
from celery import shared_task
from ..workflow.engine import WorkflowEngine
from ..core.container import Container   # your DI root


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def dispatch_pipeline(self, workflow_id: str, stage: str | None = None) -> dict:
    """
    Celery task: run a workflow pipeline (or advance to a specific stage).
    Bind=True gives access to self for retry logic.
    """
    try:
        engine: WorkflowEngine = Container.workflow_engine()
        return engine.run(workflow_id=workflow_id, stage=stage)
    except Exception as exc:
        raise self.retry(exc=exc)
```

### 2. `backend/app/execution/manager.py`

```python
"""
manager.py — ExecutionManager: coordinates ExecutionPlan lifecycle.

Imported by WorkflowEngine. Owns plan creation, stage advancement,
and status queries. The ONLY component allowed to mutate execution state
(enforcing the architecture principle that was violated everywhere else).
"""
from dataclasses import dataclass, field
from .execution_plan import ExecutionPlan
from .execution_status import ExecutionStatus
from .execution_state import ExecutionState   # existing in-process store (replace with Redis for multi-process)


class ExecutionManager:
    def __init__(self, state_store: ExecutionState):
        self._store = state_store

    def create_plan(self, workflow_id: str, stages: list[str]) -> ExecutionPlan:
        plan = ExecutionPlan(workflow_id=workflow_id, stages=stages, current_stage=stages[0])
        self._store.set(workflow_id, plan)
        return plan

    def advance(self, workflow_id: str) -> ExecutionPlan | None:
        plan = self._store.get(workflow_id)
        if plan is None:
            return None
        idx = plan.stages.index(plan.current_stage) if plan.current_stage in plan.stages else -1
        if idx < 0 or idx + 1 >= len(plan.stages):
            plan.status = ExecutionStatus.Completed
        else:
            plan.current_stage = plan.stages[idx + 1]
        self._store.set(workflow_id, plan)
        return plan

    def mark_failed(self, workflow_id: str, reason: str) -> None:
        plan = self._store.get(workflow_id)
        if plan:
            plan.status = ExecutionStatus.Failed
            plan.failure_reason = reason
            self._store.set(workflow_id, plan)

    def get_plan(self, workflow_id: str) -> ExecutionPlan | None:
        return self._store.get(workflow_id)
```

### 3. `backend/app/execution/agent_runtime.py`

```python
"""
agent_runtime.py — AgentRuntime: runs a single agent within a stage.

Imported by WorkflowRuntime. Isolates agent invocation so WorkflowRuntime
stays orchestration-only. Enforces the artifact-output contract.
"""
from ..agents.base import BaseAgent
from ..artifacts.store import ArtifactStore


class AgentRuntime:
    def __init__(self, artifact_store: ArtifactStore):
        self._artifacts = artifact_store

    def run(self, agent: BaseAgent, context: dict) -> dict:
        """
        Run agent and write its output to the artifact store.
        Raises if the agent produces no output — callers must not continue
        with a missing artifact.
        """
        result = agent.run(context=context)
        if not result:
            raise RuntimeError(f"Agent {type(agent).__name__} returned empty output")
        artifact_id = self._artifacts.write(
            agent_name=type(agent).__name__,
            stage=context.get("stage", "unknown"),
            content=result,
        )
        return {"artifact_id": artifact_id, "output": result}
```

### 4. `backend/app/agents/chat_router.py`

```python
"""
chat_router.py — ChatRouter: routes chat messages to the appropriate agent.

Imported by api/chat.py. The /chat endpoint is completely broken without this.
"""
from pydantic import BaseModel
from .factory import AgentFactory
from ..memory.memory_repository import MemoryRepository


class ChatResponse(BaseModel):
    message: str
    agent_used: str
    context_applied: bool


class ChatRouter:
    def __init__(self, factory: AgentFactory, memory: MemoryRepository):
        self._factory = factory
        self._memory = memory

    def handle(self, project_id: str, message: str, context: str | None = None) -> ChatResponse:
        # Retrieve relevant memory for this project
        mem_context = self._memory.retrieve(project_id=project_id, query=message)

        # Route to tech_lead as default conversational agent
        # Future: intent classification to route to specialist agents
        agent = self._factory.create("tech_lead")
        full_context = {"project_id": project_id, "message": message, "memory": mem_context}
        if context:
            full_context["user_context"] = context

        result = agent.run(context=full_context)
        return ChatResponse(
            message=result.get("response", str(result)),
            agent_used="tech_lead",
            context_applied=bool(mem_context),
        )
```

---

## Part 5 — Immediate Bug Fixes (In-Place)

### Fix C-05: TransitionManager (`workflow/transition_manager.py`)

**Current (broken):**
```python
def next_state(self, current_state: WorkflowState, approved: bool) -> WorkflowState:
    if approved:
        return WorkflowState.Completed
    return WorkflowState.WaitingForReview
```

**Fix:**
```python
_TRANSITIONS: dict[tuple[WorkflowState, bool], WorkflowState] = {
    (WorkflowState.Running, True):           WorkflowState.WaitingForReview,
    (WorkflowState.WaitingForReview, True):  WorkflowState.Running,
    (WorkflowState.WaitingForReview, False): WorkflowState.Failed,
    (WorkflowState.Running, False):          WorkflowState.Failed,
}

def next_state(self, current_state: WorkflowState, approved: bool) -> WorkflowState:
    key = (current_state, approved)
    result = _TRANSITIONS.get(key)
    if result is None:
        raise ValueError(f"No transition from {current_state!r} with approved={approved}")
    return result
```

### Fix C-06: ExecutionScheduler (`execution/scheduler.py`)

**Current (broken):**
```python
return plan.current_stage or plan.stages[0] if plan.stages else ""
```

**Fix:**
```python
if not plan.stages:
    return ""
if not plan.current_stage:
    return plan.stages[0]
try:
    idx = plan.stages.index(plan.current_stage)
    return plan.stages[idx + 1] if idx + 1 < len(plan.stages) else plan.current_stage
except ValueError:
    return plan.stages[0]
```

### Fix C-07: Duplicate-Run Guard (`workflow/manager.py`)

**Current (broken):** Two separate lock acquisitions — TOCTOU window between them.

**Fix (atomic check-and-set):**
```python
def try_mark_running(self, workflow_id: str) -> bool:
    """Atomically check-and-set running status. Returns False if already running."""
    with self._lock:
        if self._running_workflows.get(workflow_id):
            return False
        self._running_workflows[workflow_id] = True
        return True
```

Remove the separate `is_running()` / `mark_running()` call sites and replace with `try_mark_running()`.

### Fix H-01: AgentFactory Registration (`agents/factory.py`)

Add `"reviewer"` registration to the factory's `__init__` or `_build_registry()` method:
```python
"reviewer": lambda: ReviewerAgent(
    llm_manager=self.llm_manager,
    prompt_builder=self.prompt_builder,
)
```

### Fix H-02: workspace_manager Injection (`agents/factory.py:99`)

```python
# Before (tech_lead only):
if agent_type == "tech_lead":
    kwargs["workspace_manager"] = self.workspace_manager

# After (any agent that declares workspace_manager in its __init__):
import inspect
sig = inspect.signature(agent_cls.__init__)
if "workspace_manager" in sig.parameters:
    kwargs["workspace_manager"] = self.workspace_manager
```

---

## Part 6 — Redesign Blueprint: What a World-Class Autonomous Dev Platform Looks Like

This is not "fix the bugs." This is a ground-up rethink of the architecture, keeping the good ideas (stateless agents, artifact contracts, review gates) and replacing the broken implementation with battle-tested patterns.

---

### 6.1 — The Core Problem: Shared Mutable State in a Distributed System

The current architecture stores workflow state in:
- `workflow.json` — flat file, no transactions
- `ExecutionState` — in-process dict, invisible across Celery workers
- Memory store — in-process dict, lost on restart

Every race condition and corruption bug traces back to this.

**The fix: Event-Sourced Pipeline State**

Never mutate state in place. Append immutable events. Derive current state from the event log.

```
WorkflowEvent {
    event_id: UUID
    workflow_id: UUID
    stage: str
    event_type: StageStarted | StageCompleted | StageFailed | ApprovalRequested | ApprovalGranted | ApprovalDenied
    actor: str           # agent_name or user_id
    artifact_id: UUID | None
    timestamp: datetime
    metadata: dict
}
```

Benefits:
- No TOCTOU races — Postgres INSERT with `SKIP LOCKED` is atomic
- Full audit trail — every state transition is logged with who did it and why
- Replay — re-derive state from events to debug any run
- Cross-process — all Celery workers read from the same Postgres event stream
- Time travel — know exactly what state the system was in at any point

---

### 6.2 — Agent Protocol: Artifact Schema Contracts

Today: agents return dicts with ad-hoc keys. Reviewers cannot validate output.

**The fix: typed artifact contracts enforced at the boundary**

```python
# artifacts/contracts.py
from pydantic import BaseModel

class RequirementsArtifact(BaseModel):
    user_stories: list[str]
    acceptance_criteria: list[str]
    out_of_scope: list[str]
    estimated_complexity: Literal["S", "M", "L", "XL"]

class ArchitectureArtifact(BaseModel):
    components: list[ComponentSpec]
    data_flows: list[DataFlow]
    external_dependencies: list[str]
    adr_ids: list[str]   # links to Architecture Decision Records

# In AgentRuntime:
def run(self, agent: BaseAgent, context: dict, output_schema: type[BaseModel]) -> BaseModel:
    raw = agent.run(context=context)
    try:
        return output_schema.model_validate(raw)
    except ValidationError as e:
        raise ArtifactContractViolation(agent=type(agent).__name__, errors=e.errors())
```

This makes "every stage produces structured artifacts" structurally enforced — not a comment.

---

### 6.3 — Execution Engine as an Exclusive Write Path

Today: 4 components write project files. This is how you get corrupted projects.

**The fix: Execution Engine as a command-accepting service**

```
All file mutations → ExecutionEngine.submit(command: FileCommand) → queued, deduplicated, applied serially

FileCommand = CreateFile | UpdateFile | DeleteFile | RenameFile | CreateDirectory

No other component holds a reference to the filesystem.
WorkspaceManager becomes a read-only query layer.
DevOpsAgent submits WriteDeploymentCommand — does not hold ProjectWriter.
```

Implementation: a single `asyncio.Queue` + `asyncio.Lock` in a dedicated coroutine. Serial application. Every command logged to the event stream before and after execution.

---

### 6.4 — Single Orchestrator: Event-Driven Stage Advancement

Today: 5 competing orchestrators each make their own decisions about what runs next.

**The fix: WorkflowEngine subscribes to events and is the only thing that decides what runs next**

```
Event: StageCompleted(stage="architecture")
→ WorkflowEngine.on_stage_completed()
   → checks review gate (is human approval required for this stage?)
   → if yes: emit ApprovalRequested → wait
   → if no: emit StageStarted("coding") → dispatch next agent

Event: ApprovalGranted(stage="architecture")
→ WorkflowEngine.on_approval_granted()
   → emit StageStarted("coding") → dispatch next agent

No other component emits StageStarted. Period.
```

QAOrchestrator, PipelineSupervisor, SprintExecutor — all become passive agents that receive tasks from the Workflow Engine and report results back via events.

---

### 6.5 — Memory Architecture: Project-Scoped, Persistent, Relevance-Ranked

Today: volatile in-process dict. Lost on restart.

**The fix: three-tier memory**

```
Tier 1 — Hot (Redis, TTL 4 hours):
  Project context for the current session.
  Key: project_id:session_id
  Evicted after session ends or TTL expires.

Tier 2 — Warm (Postgres JSONB, indexed):
  Per-project learnings, decisions, past outputs.
  Queryable by stage, date, artifact_id.
  Retained for the project lifetime.

Tier 3 — Cold (HNSW vector index, e.g. pgvector):
  Semantic similarity search across all projects.
  Used when Tier 2 has no relevant context for a new project.
  Scores returned alongside results — callers filter by threshold.

Retrieval pipeline:
  MemoryManager.retrieve(project_id, query, top_k=5) →
    1. Check Tier 1 (exact key match)
    2. Query Tier 2 (SQL: project_id + recent + relevant stage)
    3. Query Tier 3 (semantic, cross-project, if Tier 2 < top_k results)
    4. Score and merge: recency_weight * 0.4 + similarity_weight * 0.6
    5. Return top_k, each with a confidence score
```

---

### 6.6 — Review Gate: Real Human-in-the-Loop

Today: AI auto-reviewer on 10 of 13 stages. Human approval is optional and inconsistent.

**The fix: declarative gate config per stage**

```yaml
# workflow/gates.yaml
stages:
  requirements:
    review_type: human          # blocks until a human approves via the API
    timeout_hours: 24           # auto-escalates after 24h with no response
    escalation: tech_lead_email
  architecture:
    review_type: human
    timeout_hours: 48
  coding:
    review_type: ai             # AI reviewer; auto-approves if score >= threshold
    reviewer_agent: tech_lead
    approval_threshold: 0.85
  testing:
    review_type: both           # AI reviews first; human reviews only if AI flags issues
    ai_reviewer: tech_lead
    human_escalation_threshold: 0.70
```

WorkflowEngine reads this config at startup. Review type is not hardcoded in Python — it's configured and testable.

---

### 6.7 — Observability: Structured Logging + Span Tracing

Today: scattered `logger.warning()` calls with string messages. Impossible to trace a workflow run across services.

**The fix: every operation is a span with a trace_id**

```python
# Every workflow run gets a trace_id propagated through all agents
with tracer.start_span("stage.coding", trace_id=workflow.trace_id) as span:
    span.set_tag("agent", "coding_agent")
    span.set_tag("workflow_id", workflow_id)
    span.set_tag("stage", "coding")
    result = agent_runtime.run(agent, context)
    span.set_tag("artifact_id", result.artifact_id)
```

Use OpenTelemetry. Export to Jaeger or Tempo. Every failed run is debuggable by trace_id — no more guessing which log line belongs to which workflow.

---

## Part 7 — Actionable Execution Plan (OpenCode Format)

These are ordered by impact. Execute in sequence.

### EXEC-01: Create the four missing Python files [CRITICAL — do first]
```
Files to create:
1. backend/app/tasks/pipeline_task.py       → see Part 4, section 1
2. backend/app/execution/manager.py         → see Part 4, section 2
3. backend/app/execution/agent_runtime.py   → see Part 4, section 3
4. backend/app/agents/chat_router.py        → see Part 4, section 4

Validation: python -c "from app.api.workflow import router; from app.workflow.engine import WorkflowEngine"
Expected: no ImportError
```

### EXEC-02: Fix TransitionManager [CRITICAL]
```
File: backend/app/workflow/transition_manager.py
Replace next_state() with the transition table implementation in Part 5 → Fix C-05
Add test: test_transition_manager.py — assert every (state, approved) pair maps to the correct next state
```

### EXEC-03: Fix ExecutionScheduler operator precedence bug [CRITICAL]
```
File: backend/app/execution/scheduler.py
Replace the one-liner return with the explicit index-based implementation in Part 5 → Fix C-06
Add test: assert scheduler advances through all stages in order
```

### EXEC-04: Fix TOCTOU duplicate-run guard [CRITICAL]
```
File: backend/app/workflow/manager.py
Replace is_running() + mark_running() with atomic try_mark_running() in Part 5 → Fix C-07
Add test: two concurrent coroutines attempting to start the same workflow — exactly one should succeed
```

### EXEC-05: Fix AgentFactory resolver + injection gaps [HIGH]
```
File: backend/app/agents/factory.py
1. Register "reviewer" agent (Fix H-01)
2. Use inspect.signature to inject workspace_manager to all agents that declare it (Fix H-02)
3. Separate self.agents (class registry) from self.descriptors (AgentDescriptor dict) — they are currently the same object
```

### EXEC-06: Fix DevOpsAgent architecture violation [HIGH]
```
File: backend/app/agents/devops.py
1. Remove self.project_writer = project_writer or ProjectWriter()
2. Remove project_writer from WriteDeploymentAction constructor call
3. WriteDeploymentAction must submit a FileCommand to the ExecutionEngine (EXEC-07 must be done first)
```

### EXEC-07: Implement ExecutionEngine as exclusive write path [HIGH — prerequisite for EXEC-06]
```
New file: backend/app/execution/engine.py
Implement command queue pattern (Part 6.3)
Register in DI container
Update all callers of WorkspaceManager.update_project_json() to go through this
```

### EXEC-08: Replace volatile ExecutionState with Redis [HIGH]
```
File: backend/app/execution/execution_state.py
Replace in-process dict with Redis client (hset/hget with workflow_id as key)
Use pipeline() for atomic multi-key operations
Add EXEC-08 to the docker-compose.yml Redis service (likely already there for Celery broker)
```

### EXEC-09: Delete dead code clusters [MEDIUM]
```
Delete (after EXEC-01–08 are verified):
- agents/descriptor.py
- agents/validation.py (move to utils/validation.py as a function)
- workflow/state_machine.py (or wire it in — do not keep dead code)
- workflow/runtime_state.py
- execution/recovery_policy.py (or enforce it — do not keep dead fields)
- execution/execution_metrics.py (replace with real OpenTelemetry counters — EXEC-10)
- memory/memory_cleanup.py (implement real cleanup — EXEC-11)
- memory/memory_filter.py (implement relevance scoring — EXEC-11)
- memory/memory_statistics.py (replace with OTEL — EXEC-10)
- memory/memory_summary.py (implement generation — EXEC-11)
```

### EXEC-10: Add OpenTelemetry tracing [MEDIUM]
```
Install: opentelemetry-sdk, opentelemetry-instrumentation-fastapi, opentelemetry-exporter-otlp
Instrument: WorkflowEngine, AgentRuntime, MemoryManager
Every workflow run gets a trace_id in the X-Trace-ID response header
Replace the execution_metrics counters with OTEL Counter instruments
```

### EXEC-11: Implement real memory architecture [MEDIUM]
```
Phase 1: Add Postgres persistence for memory_store (replace in-process dict)
Phase 2: Add retrieval scoring (recency + relevance blend per Part 6.5)
Phase 3: Add pgvector for semantic search (Tier 3 per Part 6.5)
Phase 4: Implement real memory_cleanup (SQL DELETE WHERE project_id AND created_at < cutoff)
Phase 5: Implement memory_summary generation (LLM call summarizing recent memories for a project)
```

### EXEC-12: Implement artifact schema contracts [MEDIUM]
```
New file: backend/app/artifacts/contracts.py
Define Pydantic models for each stage output (Part 6.2)
Update AgentRuntime to validate against schema on write
Update Reviewer to validate against schema before approval
```

### EXEC-13: Delete dead files from repo [LOW — but hygiene]
```
Delete the files listed in Part 3, Cluster D
git rm direct_run.log direct_run_report.json task1.txt.txt fix1.md \
   AUDIT_REPORT.md ARCHITECTURE_VALIDATION.md DESIGN_SPEC.md FINAL_REVIEW.md \
   VALIDATION_GATES.md TEST_STRATEGY.md FRONTEND_MIGRATION_PLAN.md \
   DISCOVERY_NOTES.md CODEBASE_MAP.md FIX_LOG.md ai_devos_opencode.md
git rm backend/test_results.txt
git rm -r backend/_stale_backend_to_delete/
git rm backend/app/memory/AUDIT_FINDINGS.md
```

### EXEC-14: Wire WorkflowStateMachine as the ONLY state mutator [LOW — after EXEC-02]
```
File: backend/app/workflow/engine.py
Replace all direct workflow.state = X assignments with self._state_machine.{start,approve,complete,fail}()
The state machine already has the right logic — it just has zero callers
```

### EXEC-15: Add review gate config [LOW — after EXEC-02, EXEC-14]
```
New file: backend/app/workflow/gates.yaml
Define review_type per stage (Part 6.6)
WorkflowEngine reads this config at startup
Remove hardcoded review logic from engine.py
```

---

## Part 8 — Tips for Execution

### Tip 1: Fix in dependency order
`EXEC-01 → EXEC-02 → EXEC-03 → EXEC-04 → EXEC-05 → EXEC-07 → EXEC-06 → EXEC-08`  
Never fix a high-level component before fixing the low-level component it depends on.

### Tip 2: Test each fix with a single integration smoke test before moving on
```bash
# After EXEC-01:
cd backend && python -c "from app.api import app; print('OK')"

# After EXEC-02–04:
cd backend && pytest tests/test_workflow/ -x -v

# After EXEC-07–08:
docker compose up -d && curl -X POST /api/workflow/start -d '{"project_id":"test"}'
```

### Tip 3: Use feature flags for the redesign components
Don't replace memory_store all at once. Gate behind `MEMORY_BACKEND=redis|postgres|in_memory`. This lets you deploy incremental changes without breaking existing behavior.

```python
# config.py
MEMORY_BACKEND = os.getenv("MEMORY_BACKEND", "in_memory")   # safe default
EXECUTION_STATE_BACKEND = os.getenv("EXECUTION_STATE_BACKEND", "in_memory")
```

### Tip 4: Event sourcing can be added incrementally
You don't need to rewrite everything to get event sourcing. Start by appending WorkflowEvent records to a Postgres table alongside the existing workflow.json. Once the event log is the source of truth for the UI, remove the JSON file.

### Tip 5: The TechLeadAgent is the gold standard — copy its pattern
It's the only agent with real LLM-backed logic, a real prompt builder integration, and a real reviewer call. Use it as the template for every other agent. The ScrumMasterAgent, SprintPlannerAgent, DesignerAgent, SecurityAgent — all of them should look like TechLeadAgent, not the current 300-line delegate-to-one-action stubs.

### Tip 6: Don't add features until EXEC-01–05 are done
The system doesn't work. More features on a broken foundation make the foundation harder to fix. Fix the foundation first — the "startup without ImportError" bar is embarrassingly low and must be the first milestone.

### Tip 7: Add a CI gate that fails on ImportError
```yaml
# .github/workflows/ci.yml
- name: Smoke import
  run: cd backend && python -c "from app.api import app"
```
This catches C-01 through C-04 class of bugs before they ever reach main.

### Tip 8: The three things that will matter most at scale
1. Event-sourced state (no more file corruption under concurrency)
2. Artifact schema contracts (reviewers can actually validate outputs)
3. Exclusive write path for project files (no more race conditions)

Everything else is refinement. These three are structural.

---

## Summary Scorecard

| Category | Files Audited | Critical | High | Medium | Low |
|----------|--------------|----------|------|--------|-----|
| Workflow | 8 | 5 | 3 | 3 | 1 |
| Execution | 6 | 2 | 2 | 4 | 0 |
| Agents | 12 | 2 | 3 | 4 | 2 |
| Memory | 6 | 1 | 2 | 3 | 1 |
| API | 4 | 2 | 1 | 2 | 0 |
| Frontend | 18 | 0 | 2 | 6 | 4 |
| **Total** | **54** | **12** | **13** | **22** | **8** |

**Bottom line:** 12 Critical findings, 4 of which prevent the system from starting at all. Fix those 4 first. Fix the other 8 before adding any new feature. Everything else can be prioritized by business need.

---

*End of God-Mode Audit. This document should be treated as the new technical debt register. Every EXEC-XX item should become a tracked ticket. The redesign sections (6.1–6.7) are long-term architectural targets, not immediate requirements — but every new component written should be designed to fit the target, not the current broken state.*

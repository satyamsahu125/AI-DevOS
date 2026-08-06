# AI DevOS — Production Strategy & Architecture Review

> Written after full codebase analysis across all layers: API, Kernel, Container, 
> WorkflowEngine, PipelineSupervisor, WorkflowManager, ExecutionManager, AgentFactory, 
> ContextBuilder, ArtifactManager, MemoryManager, LLMManager, Reviewer, LearningLoop, 
> LessonStore, CheckpointManager, Intelligence Layer.

---

## 1. What You've Actually Built (Honest Assessment)

This is a **well-designed research prototype** that has crossed into working software. The
core architectural ideas are correct: stateless agents, single-slot predecessor messages,
artifact-driven stages, three-tier review, learning loops. Several of these are genuinely
sophisticated. But the system has accumulated technical debt from rapid iteration, and
several foundational production requirements are missing entirely.

**What works and is well-designed:**
- 19-stage pipeline with configurable retry policy
- Three-tier Reviewer (AUTO_FIX / ASK_HUMAN / FLAG) — solid quality gate logic
- WorkflowEngine's enrichment pipeline (`_with_predecessor_message`, `_with_design_context`, `_with_lessons`, `_with_relevant_patterns`)
- CheckpointManager for crash recovery (correct design, partial implementation)
- LearningLoop + LessonStore — genuinely useful pattern injection
- LLMManager with tenacity retry + multi-provider support
- ArtifactManager with versioned attempt files
- WebSocket event broadcasting with loop binding fix
- DependencyContainer singleton registration

**What is broken or critically fragile:**
- Context assembly for ProductOwner (just fixed but reveals a systemic pattern)
- OLLAMA_* env vars bleeding into all providers (partially fixed)
- No authentication on any API endpoint
- Pipeline runs in raw `threading.Thread` — no queue, no backpressure, no isolation
- Multiple disconnected SQLite databases with no schema migrations
- Artifacts on local disk — lost on container restart
- MemoryOrchestrator registered but disabled; ContextManager disabled
- Intelligence layer (FileIndexer, DependencyGraph, ContextOrchestrator) wired but optional and untested in production

---

## 2. Critical Bugs Still in the System

These will cause failures in production without fixes.

### 2.1 Single-Slot Predecessor Memory is Structurally Unsafe

`_WORKFLOW_MESSAGE_KEY = "workflow:latest_message"` stores only ONE message per project.
Every stage approval overwrites the previous one. This means stages that need data from
two stages ago (not just the immediate predecessor) must be specially handled
(like the `_with_design_context` and `_with_clarification_context` we added).

Every stage that needs non-adjacent context has this bug silently. **Architect needs
the RequirementsArtifact. Designer needs the ArchitectureArtifact. QA needs the
SprintPlan.** These all pass through the single slot — but in a 19-stage pipeline,
by the time you reach stage 12, slot stage 2's data is long gone.

**Fix:** Replace the single-slot key with a per-stage namespace:
`workflow:stage:{stage_name}` — store every stage's approval independently so any
stage can read any predecessor.

### 2.2 Background Thread Pipeline Has No Isolation

```python
threading.Thread(target=_run, daemon=True, name=f"workflow-{project_id}").start()
```

There is no limit on how many threads can be created. Two requests for the same
`project_id` create two threads that both write to the same artifact files and the
same SQLite databases. SQLite's write serialization will corrupt data under concurrent
writes to the same DB. There is also no way to cancel a running pipeline gracefully —
`daemon=True` just kills the thread on process exit, without cleanup.

**Fix:** Use a proper task queue (Celery + Redis, or an async queue). One pipeline per
project, queued if one is already running.

### 2.3 All SQLite Databases Have No Migration System

The system has at least 8 separate SQLite files:
`memory.sqlite`, `knowledge.sqlite`, `learning.sqlite`, `lessons.sqlite`, 
`costs.sqlite`, `sessions.db`, `file_index.db`, `data/memory.sqlite`.

None have a schema migration system. If any table definition changes, the database
silently uses the old schema until it crashes with a cryptic column-not-found error.

**Fix:** Add Alembic (or a simple migration table) to each database.

### 2.4 `Stage.Clarification` May Not Exist in the Enum

The fix for ProductOwner context calls `self.artifact_manager.get_artifact(project_id, Stage.Clarification)`.
If `Stage.Clarification` is not defined in the `Stage` enum, this raises `AttributeError`
and silently falls back to empty context — the same bug we just fixed. Verify it exists:

```python
# Check: does Stage.Clarification exist?
from app.shared.enums.stage import Stage
hasattr(Stage, 'Clarification')  # must be True
```

### 2.5 Cost Tracker Hardcodes Database Path

```python
CostTracker("backend/app/memory/costs.db")
```

This is a relative path resolved from wherever `uvicorn` is started. If started from a
different directory, costs.db is created in the wrong place or raises FileNotFoundError.
**Fix:** Use `Path(__file__).parent` to anchor all database paths.

### 2.6 No Request Validation on Project Description

A user can send a 500,000-character project description. This gets embedded in every
stage's LLM prompt, burning tokens on every call. There is no length limit, no
sanitization, and no rejection of clearly malicious input.

---

## 3. Architectural Issues (Design Debt)

### 3.1 Context Assembly is Ad-Hoc Per Stage

Every stage that needs non-standard context requires a custom enrichment method in
`WorkflowEngine`. We now have:
- `_with_predecessor_message` — for the immediately preceding stage
- `_with_design_context` — for FrontendDeveloper/QA needing the approved design
- `_with_clarification_context` — for ProductOwner needing Q&A answers (just added)
- `_with_relevant_patterns` — for LearningLoop patterns
- `_with_lessons` — for LessonStore lessons
- `_with_intelligence_context` — for FileIndexer/DependencyGraph

This will grow indefinitely as more stages need non-adjacent data. The disabled
`ContextManager` class is the right idea — it just needs to be finished and wired in.

**Correct design:** A `ContextAssembler` that is given a `(project_id, stage_name)` and
returns a complete, typed context object by loading all relevant artifacts, memory
entries, and intelligence data. Stages declare what they need, the assembler provides it.
No ad-hoc per-stage hacks.

### 3.2 Prompt Builders Have Three Incompatible Input Paths

`ProductOwnerPromptBuilder.build()` has Path A (JSON dict), Path B (predecessor string),
and Path C (plain text). This was added to handle the different ways context arrives —
which is itself a symptom of 3.1. The other prompt builders likely have similar
workarounds. Every new input format becomes a new code path.

**Correct design:** All prompt builders receive a typed `AgentContext` dataclass. No string
parsing, no Path A/B/C branching.

### 3.3 WorkflowManager is a God Class

`workflow/manager.py` handles: Q&A session management, StrategicReview execution,
artifact saving, state transitions, sprint execution, requirement change processing, and
pipeline resumption. It is 600+ lines and violates the Single Responsibility Principle.

`PipelineSupervisor` was created to extract some of this, but `WorkflowManager` still
owns too much. The `_handle_qa_flow` method alone is 200+ lines.

### 3.4 Container Wiring is 300 Lines of Manual Code

`container.py` manually wires 30+ singletons by name with no type safety. A typo in
`"artifact_manager"` silently resolves to `None` at startup but crashes at runtime.
`resolve("lesson_store")` is wrapped in a `try/except` because it might not be registered.

**Fix:** Use a proper DI framework (Python's `dependency-injector`, or at minimum typed
factory functions with runtime validation at startup).

### 3.5 Intelligence Layer is Wired but Not Validated

`FileIndexer`, `ProjectDependencyGraph`, `CodeSummarizer`, `ContextOrchestrator`, and
`SprintMonitor` are all instantiated in the container but their contributions are gated
behind `if self.context_orchestrator is None: return content`. In practice, because the
`lesson_store` resolution can fail, the ContextOrchestrator may be silently None.

**Fix:** Add a startup health check that validates every registered singleton is non-None
and reachable.

---

## 4. Production Readiness Gaps

### 4.1 No Authentication (Critical)

Zero authentication on any API endpoint. Anyone who can reach port 8000 can:
- Create unlimited projects (burning your Bedrock credits)
- Read any project's artifacts
- Submit fake QA answers
- Trigger pipeline stages

**Fix:** Add OAuth2/JWT via `fastapi-users` or a simple API key middleware as a minimum.

### 4.2 No LLM Cost Controls

There is a `CostTracker` but:
- No budget limit per project
- No kill switch when budget is exceeded
- No real-time cost visibility to the caller
- Bedrock charges ~$0.22/M input tokens + $0.88/M output tokens; a 19-stage pipeline with
  8192 output tokens per stage costs ~$1.50–$3.00 per project at current prices

**Fix:** Add `MAX_COST_PER_PROJECT` env var. CostTracker emits a `budget_exceeded` event
that the WorkflowEngine checks before each attempt.

### 4.3 No Streaming to the Client

Every LLM call collects the full response (up to 8192 tokens) before returning. The user
sees nothing for 10–30 seconds, then gets the full output. The `BedrockProvider` and
`GeminiProvider` both have `stream()` methods but they yield the full response in one shot.

**Fix:** Implement actual streaming via Server-Sent Events (SSE) or WebSocket chunks.
Bedrock's `InvokeModelWithResponseStream` API supports token-level streaming.

### 4.4 Artifacts on Local Disk

All project artifacts, workspace files, and generated code are in `backend/temp-workspace/`.
On a container restart, pod reschedule, or disk failure, every project is lost.

**Fix:** Use object storage (S3, GCS, or MinIO) with a local cache. `ArtifactManager`
already has an abstraction layer — replace the file backend with an S3 backend.

### 4.5 No Structured Logging or Observability

Log lines are plain Python `logging` with no correlation IDs. A failing pipeline produces
lines scattered across modules with no way to trace a single request through the system.

**Fix:**
- Add structured JSON logging with `project_id`, `stage_name`, `attempt` on every line
- Add OpenTelemetry spans around LLM calls and stage executions
- Add a `/metrics` endpoint (Prometheus format) for latency, token counts, stage success rates

### 4.6 No Deployment Configuration

No `Dockerfile`, no `docker-compose.yml`, no Kubernetes manifests. The only way to run
this is via `uvicorn` started by hand. Reproducible deployments are impossible.

### 4.7 SQLite is the Wrong Database for Production

SQLite serializes all writes. Under concurrent projects (even 2 running simultaneously),
writes to `memory.sqlite` will queue up. Under load, this becomes a bottleneck and
then a source of corruption. SQLite also doesn't support JSON operators efficiently —
many queries do full table scans.

**Fix:** PostgreSQL + pgvector (replaces SQLite + hnswlib for vector search). Migration
is straightforward since the schema is simple.

---

## 5. Phased Production Roadmap

### Phase 1 — Stability (2–3 weeks) — Do This First

These fix things that are actively broken or will break under normal use.

| # | Fix | Files |
|---|-----|-------|
| 1 | Verify `Stage.Clarification` enum exists; add if missing | `shared/enums/stage.py` |
| 2 | Fix predecessor slot: store per-stage (`workflow:stage:{name}`) | `workflow/engine.py` |
| 3 | Anchor all DB paths to `Path(__file__)` | `container.py`, all managers |
| 4 | Add project description length limit (max 2000 chars) | `api/project.py` |
| 5 | Add `MAX_COST_PER_PROJECT` check in WorkflowEngine before each LLM call | `workflow/engine.py`, `llm/cost_tracker.py` |
| 6 | Add Alembic for all SQLite databases | new `migrations/` directory |
| 7 | Fix `threading.Thread` → use a per-project lock to prevent duplicate runs | `api/workflow.py` |
| 8 | Add startup validation: assert all container singletons are non-None | `kernel/lifecycle.py` |

### Phase 2 — Hardening (3–4 weeks)

| # | Fix | Impact |
|---|-----|--------|
| 9 | Add API key authentication (header: `X-API-Key`) | Prevents credit theft |
| 10 | Implement `ContextAssembler` — replace all `_with_*` methods | Eliminates context bugs |
| 11 | Typed `AgentContext` dataclass → all prompt builders receive this, no Path A/B/C | Eliminates prompt parsing bugs |
| 12 | Wire `ContextManager` (it's already written but disabled) | Enables intelligence layer |
| 13 | Add Bedrock streaming (`InvokeModelWithResponseStream`) | Real-time output |
| 14 | Add `Dockerfile` + `docker-compose.yml` | Reproducible deployment |
| 15 | Replace `MemoryOrchestrator` (currently disabled) with a working implementation | Enables cross-stage memory |

### Phase 3 — Production Infrastructure (4–6 weeks)

| # | Fix | Impact |
|---|-----|--------|
| 16 | Replace SQLite with PostgreSQL + pgvector | Concurrent projects, proper indexing |
| 17 | Replace local artifact files with S3/MinIO | Persistent storage, multi-instance |
| 18 | Add Celery + Redis task queue for pipeline execution | Proper backpressure, cancellation |
| 19 | Add OpenTelemetry tracing (spans per stage, per LLM call) | Observability |
| 20 | Add structured JSON logging with correlation IDs | Debuggability |
| 21 | Add Prometheus `/metrics` endpoint | Monitoring |
| 22 | Add API rate limiting per API key | Abuse prevention |
| 23 | Split `WorkflowManager` into `QASessionManager` + `PipelineOrchestrator` | Maintainability |

### Phase 4 — Scale (ongoing)

| # | Fix | Impact |
|---|-----|--------|
| 24 | Multi-model routing: cheap model for simple stages, expensive for critical ones | 50–70% cost reduction |
| 25 | Prompt caching (Bedrock/Anthropic system prompt caching) | Latency + cost reduction |
| 26 | Parallel sprint execution (multiple files in the same sprint, parallelized) | Speed |
| 27 | Shared knowledge base across projects (domain research reuse) | Quality + speed |
| 28 | Fine-tuned model for each stage based on LearningLoop data | Quality |

---

## 6. The One Structural Fix That Unlocks Everything

**Replace the single predecessor slot with per-stage storage.**

Currently: `memory_manager.store(project_id, "workflow:latest_message", ...)` — one slot,
overwritten every stage.

What it should be:
```python
# On stage approval:
memory_manager.store(project_id, f"workflow:stage:{stage.value}", message.model_dump_json())

# On stage start (context assembly):
def get_stage_context(project_id, stage_name, dependencies: list[str]) -> dict:
    return {
        dep: memory_manager.load(project_id, f"workflow:stage:{dep}")
        for dep in dependencies
    }
```

With this, every stage declares its dependencies and gets exactly what it needs. No
ad-hoc `_with_clarification_context`, no Path A/B/C in prompt builders, no context bugs.
The intelligence layer, LearningLoop, and LessonStore enrichment are then composable
layers on top of this base context. This is what the disabled `ContextManager` was trying
to be — finish it.

---

## 7. Active Pipeline Bug: Two-Layer Clarification Failure

This is the bug currently blocking every project from completing ProductOwner. It has
two independent root causes — fixing only one leaves the other as a latent failure mode.

### The Execution Path That Causes It

```
ProjectInitializer.initialize()
  → workspace.update_state(CLARIFYING)

WorkflowManager.run()
  → state == CLARIFYING
  → _handle_clarifying_state()
    → _run_domain_research()         ✓  DomainResearch.json saved
    → agent.generate_questions()     ✗  returns [] (empty list, no exception)
    → if questions: ...              ✗  skipped — questions is empty
    → else:                          ← BUG A fires here
        _run_stage("StrategicReview", request)   ← no QA answers, no Clarification artifact
        _transition(REQUIREMENTS_READY)
        _pipeline_supervisor.run()   → ProductOwner starts

WorkflowEngine.run("ProductOwner")
  → _with_clarification_context()
    → artifact_manager.get_artifact(project_id, Stage.Clarification)  → None
    → clarification_struct = {}      ← BUG B fires here
    → return json.dumps({"clarification": {}, ...})

ProductOwnerPromptBuilder.build()
  → clarification is {}
  → model says: "Clarification artifact is empty"
  → produces requirements: []

Reviewer checks WriteRequirements:
  → requirements in _CRITICAL_SCHEMAS
  → empty → ASK_HUMAN → reject

WorkflowEngine retries 3×:
  → same empty context each time → same rejection

PipelineSupervisor: stage product_owner failed
```

### Bug A — Silent QA Bypass (Triggering Bug)

**File:** `backend/app/workflow/manager.py`, method `_handle_clarifying_state()`

The 3-attempt retry loop generates clarification questions. If the LLM returns valid JSON
with `questions: []` (no exception — just an empty list), the loop completes all three
attempts silently and falls to the `else` branch at line 312. That branch runs
StrategicReview directly from `original_request` with no QA, then immediately calls
`_pipeline_supervisor.run()`. No `Clarification.json` artifact is ever saved to disk.
No user notification is sent. Execution continues as if QA completed normally.

**Confirmed from project.json:**
```json
"clarification": {
  "questions_asked": [],
  "answers_received": [],
  "complete": false
}
```
No `Clarification.json` in `temp-workspace/{id}/artifacts/` — artifact was never written.

**The Fix:** In the `else` branch, before calling `_pipeline_supervisor.run()`, construct
and save a minimal Clarification artifact from `original_request`. This ensures ProductOwner
always has a non-empty clarification context even when QA is bypassed:

```python
# else branch in _handle_clarifying_state() — QA was skipped
minimal_clarification = {
    "original_request": request,
    "project_description": request,
    "functional_requirements": [],
    "non_functional_requirements": [],
    "scale_profile": {
        "user_count": "unknown",
        "auth_needed": False,
        "database_needed": False,
        "infrastructure_tier": "unknown",
    },
    "explicit_non_requirements": [],
    "open_questions": [],
    "inferred_scope": "QA was skipped — proceeding with original request only",
}
self.artifact_manager.save_artifact(
    project_id=project_id,
    stage=Stage.Clarification,
    content=json.dumps(minimal_clarification, indent=2),
    structured_content=minimal_clarification,
)
```

Also add a log warning so the bypass is visible in the logs:
```python
logger.warning(
    "QA bypassed for %s: question generation returned empty. "
    "Saving minimal clarification artifact and proceeding.",
    project_id,
)
```

### Bug B — Missing Fallback in Context Assembly (Defense in Depth)

**File:** `backend/app/workflow/engine.py`, method `_with_clarification_context()`

Even after Bug A is fixed, if question generation ever fails again (different error path,
new LLM provider, timeout), `Clarification.json` may not exist. Currently the method
falls back to `clarification_struct = {}` when `get_artifact()` returns `None`. The model
receives an empty JSON object for its PRIMARY input and has nothing to derive requirements
from.

**The Fix:** When no Clarification artifact exists, build a meaningful fallback from
`project.json` rather than passing `{}`. The model can produce reasonable requirements
from a description string alone — it cannot produce anything useful from `{}`:

```python
clarification_artifact = self.artifact_manager.get_artifact(project_id, Stage.Clarification)

if clarification_artifact is None:
    # No QA was done — build a minimal context from project.json
    p_data = self.workspace_manager.load_project_json(project_id) or {}
    original_request = p_data.get("original_request") or p_data.get("description") or content
    clarification_struct = {
        "original_request": original_request,
        "project_description": original_request,
        "inferred_scope": "No clarification was performed. Infer scope from the request.",
        "functional_requirements": [],
        "scale_profile": {
            "user_count": "unknown",
            "auth_needed": False,
            "database_needed": False,
        },
    }
    logger.warning(
        "_with_clarification_context: no Clarification artifact for %s. "
        "Using project.json fallback — model will infer scope.",
        project_id,
    )
else:
    clarification_struct = (
        getattr(clarification_artifact, "structured_content", None) or {}
    )
```

### Why Both Fixes Are Necessary

Bug A prevents the artifact from being written. Bug B is what happens when the artifact
is missing regardless of why. Fixing only Bug A means a future timeout, a model error, or
a test that bypasses QA via a different code path will silently send `{}` to ProductOwner
again. The fixes are independent: Bug A is a write-path gap, Bug B is a read-path gap.
Together they make the system resilient to any QA failure mode.

### Impact on Downstream Stages

The Clarification artifact is the PRIMARY input for ProductOwner and propagates downstream:
- **ProductOwner** reads `clarification` as its main context → produces Requirements
- **Architect** reads `scale_profile` from Clarification → determines if backend is needed
- **Designer** reads `infrastructure_tier` from Clarification → determines UI complexity
- **Security** reads `auth_needed` from Clarification → determines auth requirements

When `clarification: {}` reaches ProductOwner, all `scale_profile` values are unknown,
which causes Architect to default to the most complex architecture and Security to add
unnecessary auth requirements. The minimal fallback built by Bug B's fix prevents this
cascade even when QA is bypassed.

---

## 8. Memory Architecture: Four-Layer Design

The current system has 7 disconnected SQLite databases with no unified access layer.
Each component manages its own store independently:

```
MemoryManager     → memory.sqlite      (key/value, single-slot predecessor)
KnowledgeBase     → knowledge.sqlite   (vector search, embeddings)
LearningLoop      → learning.sqlite    (cross-project patterns)
LessonStore       → lessons.sqlite     (stage-specific lessons)
CostTracker       → costs.sqlite       (billing records)
FileIndexer       → file_index.db      (repository index)
CheckpointManager → sessions.db        (pipeline checkpoints)
```

No component can query another's data. The pipeline has no unified view of what it knows.
`ContextManager` and `MemoryOrchestrator` were written to fix this but are both disabled.
The root cause of Bug A and Bug B above is a direct consequence of this fragmentation —
the QA path writes to one store, the context assembly path reads from another, and they
never meet.

### Layer 1 — Working Memory (in-process, ephemeral)

What the pipeline holds in RAM during a single stage execution: the assembled context
object passed to the LLM. It dies when the stage completes. Currently this is a raw
string assembled by `WorkflowEngine` — no structure, no type safety, no schema.

**Target design — typed context dataclass:**

```python
@dataclass
class StageContext:
    project_id: str
    stage: Stage
    original_request: str
    predecessor_outputs: dict[str, Any]    # keyed by stage name
    clarification: ClarificationArtifact | None
    strategic_brief: dict | None
    domain_research: dict | None
    design_artifact: dict | None
    lessons: list[Lesson]
    patterns: list[Pattern]
    intelligence: ProjectIntelligence | None
    token_budget: int
    assembled_at: datetime
```

Every stage receives exactly this. `ProductOwnerPromptBuilder` gets
`context.clarification` — not a string to parse, not a JSON dict to detect, a typed
object or `None`. The Path A/B/C branching disappears entirely.

### Layer 2 — Episodic Memory (per-project, persistent)

What happened in this project across its full lifetime — across server restarts, across
sessions. Currently the single-slot `workflow:latest_message` overwrites on every stage
approval. By the time ProductOwner runs (stage 6), Clarification (stage 2) is gone.

**Target design — per-stage namespace:**

```
project:{id}:stage:DomainResearch:output     → approved artifact JSON
project:{id}:stage:Clarification:output      → QA synthesis artifact
project:{id}:stage:StrategicReview:output    → strategic brief
project:{id}:stage:ProductOwner:output       → requirements artifact
project:{id}:stage:{StageName}:attempts      → list of all attempts + reviewer feedback
project:{id}:stage:{StageName}:reviewer_log  → what the Reviewer said each attempt
project:{id}:timeline                        → ordered completions with timestamps
project:{id}:qa_session                      → raw Q&A questions and answers
```

With this, `_with_clarification_context()` becomes:

```python
return self.memory.load(project_id, "stage:Clarification:output")
```

No file lookup, no fallback logic, no special-casing. If it's there it's there. The
`_with_*` methods in `WorkflowEngine` all collapse into a single
`MemoryOrchestrator.get_context(project_id, stage)` call.

**Storage:** one SQLite file per project (isolated), or PostgreSQL with `project_id`
partitioning. The current `ArtifactManager` file-based storage is a reasonable interim
— the problem is the single-slot memory layer on top, not the artifact files themselves.

### Layer 3 — Semantic Memory (cross-project, shared)

Knowledge that accumulates across all projects the system has ever run. Currently split
across `KnowledgeBase` (vector search) and `LessonStore` (lessons), but neither has an
automatic write path from stage approvals. They must be called explicitly — and they
aren't.

**Two sub-stores:**

*Pattern Store* — vectorized embeddings of successful stage outputs. When ProductOwner
runs on "build a calculator app," semantic search retrieves approved ProductOwner
artifacts from past calculator/math projects. The model gets these as examples in its
context, dramatically improving output quality on common project types.

*Failure Store* — indexed by `(stage_name, error_type, project_category)`. When
`WriteRequirements` produces `requirements: []` with Bedrock, the failure store
records: stage=ProductOwner, error=empty_requirements, provider=bedrock,
fix=increase_max_tokens OR check_clarification_context. On the next project's
ProductOwner attempt, this lesson is injected into the prompt automatically.

**The missing write path (currently):**

```python
# Nothing calls these today — they must be wired into WorkflowEngine
on_stage_approved → knowledge_base.index(stage, artifact)      # async
on_stage_rejected → lesson_store.record(stage, feedback, fix)  # async
```

**Target write path wired into WorkflowEngine:**

```python
def _record_outcome(self, project_id, stage, result, reviewer_feedback=None):
    if result.approved:
        self.memory.record_approval(project_id, stage, result.artifact)
        # async: self.semantic.index_pattern(stage, result.artifact)
    else:
        self.memory.record_rejection(project_id, stage, reviewer_feedback)
        # async: self.semantic.index_failure(stage, reviewer_feedback)
```

### Layer 4 — Procedural Memory (structural, code-aware)

What the system knows about the project's code structure as it's being built. Answers
structural queries: "What functions does the auth module expose?" "Which files have been
modified in this sprint?" "What are the import dependencies of `main.py`?"

This is `FileIndexer`, `ProjectDependencyGraph`, and `CodeSummarizer` — already in the
codebase, already wired in `container.py`, already gated behind
`if self.context_orchestrator is None: return content`. They contribute nothing today.

**Target activation:** `MemoryOrchestrator.get_context()` always calls the procedural
layer. If it returns empty (first sprint, no files yet), that's valid. If it errors,
log and continue — don't disable it permanently. The intelligence layer becoming active
improves every code-generation stage: BackendDeveloper knows what already exists,
FrontendDeveloper knows what APIs are available, QA knows what functions to test.

### Unified Interface: MemoryOrchestrator

All four layers accessed through one interface. No stage calls individual stores directly:

```python
class MemoryOrchestrator:

    def get_context(self, project_id: str, stage: Stage) -> StageContext:
        """Called by WorkflowEngine at the start of every stage."""
        predecessor_outputs = self.episodic.get_outputs(
            project_id, dependencies=stage.declared_dependencies()
        )
        clarification = self.episodic.get_typed(project_id, Stage.Clarification,
                                                 ClarificationArtifact)
        lessons = self.semantic.get_lessons(stage, project_type=self._infer_type(project_id))
        patterns = self.semantic.get_patterns(stage, request=predecessor_outputs.get("original_request"))
        intelligence = self.procedural.get_project_state(project_id)
        return StageContext(
            project_id=project_id,
            stage=stage,
            original_request=self.episodic.get_original_request(project_id),
            predecessor_outputs=predecessor_outputs,
            clarification=clarification,
            lessons=lessons,
            patterns=patterns,
            intelligence=intelligence,
            token_budget=self._compute_token_budget(stage),
        )

    def record_approval(self, project_id: str, stage: Stage, artifact: dict) -> None:
        self.episodic.save(project_id, stage, artifact)
        self._async_index_pattern(stage, artifact)

    def record_rejection(self, project_id: str, stage: Stage,
                         feedback: ReviewFeedback) -> None:
        self.episodic.save_attempt(project_id, stage, feedback)
        self._async_index_failure(stage, feedback)
```

`WorkflowEngine.run()` becomes:

```python
def run(self, project_id, stage_name, content):
    context = self.memory_orchestrator.get_context(project_id, Stage(stage_name))
    prompt = self.agent.build_prompt(context)    # typed, no Path A/B/C
    result = self.agent.execute(prompt)
    review = self.reviewer.review(result)
    if review.approved:
        self.memory_orchestrator.record_approval(project_id, Stage(stage_name), result.artifact)
    else:
        self.memory_orchestrator.record_rejection(project_id, Stage(stage_name), review.feedback)
    return result
```

Six `_with_*` methods collapse to one `get_context()` call. Every context bug becomes
a bug in one place. Every new stage gets the correct context automatically by declaring
its dependencies — no custom enrichment methods needed.

### How Memory Design Fixes the Active Bugs

| Bug | Current cause | Memory fix |
|-----|--------------|------------|
| Bug A: Clarification artifact not saved when QA bypassed | `else` branch in `_handle_clarifying_state()` has no write to artifact store | `record_approval(Stage.Clarification, minimal)` called unconditionally at end of clarifying phase |
| Bug B: `_with_clarification_context` returns `{}` when artifact missing | Read path has no fallback | `episodic.get_typed()` returns a minimal `ClarificationArtifact` built from `original_request` — never `None` |
| Context bleeding (OLLAMA_MAX_TOKENS into Bedrock) | No typed config per provider | `StageContext.token_budget` computed per provider from typed config |
| Lessons never injected | No auto-write path from Reviewer to LessonStore | `record_rejection()` writes automatically on every Reviewer rejection |
| Intelligence layer silent | ContextOrchestrator gated behind `is None` check | `get_context()` always calls procedural layer; failure logs, doesn't disable |
| Server restart loses context | Single-slot in-memory KV | Episodic layer is persisted to disk per-project per-stage |

### Migration Path From Current System

The current components are correctly named and correctly intended. Migration is additive:

**Week 1 — Fix the immediate bug (one change):**
Change `workflow:latest_message` → `workflow:stage:{stage_name}`. This alone eliminates
the context-overwrite bug and gives all existing `_with_*` methods stable data to read.

**Week 2 — Add write path:**
Call `knowledge_base.index()` and `lesson_store.record()` from `WorkflowEngine`'s
approval/rejection paths. Patterns and lessons begin accumulating automatically.

**Week 3 — Build `MemoryOrchestrator.get_context()`:**
Implement the unified context assembly method. Replace all `_with_*` methods in
`WorkflowEngine` with a single call. Wire `ContextManager` (already written, disabled).

**Week 4 — Typed StageContext:**
Replace all prompt builder string-parsing with typed `StageContext` input. Path A/B/C
branching in `ProductOwnerPromptBuilder` and other builders disappears.

**Month 2 — Infrastructure:**
PostgreSQL + pgvector replaces all SQLite files. S3 replaces local artifact files.
Procedural layer (`FileIndexer`, `DependencyGraph`) becomes active. Episodic memory
now persists across container restarts, pod reschedules, and disk failures.

---

## 9. Project Improvements: What to Build Next

This section analyzes what the codebase already has, what it intends but doesn't finish,
and what is entirely missing — then proposes six concrete projects that would make AI DevOS
fundamentally more capable. Each project is described with its current state, the design,
and how it differs from what exists today.

---

### Project 1 — Intelligent Retry Engine (Replace Dumb Retry)

**Current state:**

`RetryPolicy` has one method: `should_retry(attempt) → attempt < max_retries`. Every
retry sends the same prompt to the same model. If the model fails because it received
empty context, retry 2 sends the same empty context. If it fails because the JSON
schema was wrong, retry 2 sends the same schema instructions. The retry loop cannot
improve because it has no memory of why the previous attempt failed.

```python
# Current: blind retry
class RetryPolicy:
    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries
```

`AgentPerformanceScorer` exists and computes a composite quality score from
`(retry_rate * 0.6) + (success_rate * 0.4)`. But its output is never used to change
retry behavior — it's a read-only diagnostic endpoint.

**The design:**

An `IntelligentRetryEngine` that reads the Reviewer's rejection feedback and changes
the retry differently depending on WHY the previous attempt failed:

```
REJECTION REASON              → RETRY STRATEGY
────────────────────────────────────────────────────────────────────
empty_required_field          → inject field-specific reminder into prompt
                                + increase max_tokens by 50%
schema_mismatch               → inject exact schema with example JSON
                                + set temperature=0.1
context_missing               → rebuild context from memory layer
                                (don't just re-run same prompt)
ask_human (critical schema)   → escalate immediately, don't retry
                                (this is Bug B's case)
low_quality_content           → inject lesson from LessonStore
                                + use a stronger model for next attempt
token_truncated               → reduce input context by 30%
                                + increase output max_tokens
```

The Reviewer already classifies rejections into types (AUTO_FIX, ASK_HUMAN, FLAG) and
produces structured feedback. The retry engine reads this feedback to decide strategy.

**How it differs:** Current retry is `attempt < 3`. The new retry is
`strategy = plan_retry(reviewer_feedback, attempt, stage_history)`. Each retry is
meaningfully different from the last. A stage that fails 3 times for different reasons
today just exhausts retries. With intelligent retry, the first failure diagnoses the
problem, the second attempt addresses it specifically.

**Integration point:** `WorkflowEngine.run()` currently calls `retry_policy.should_retry(attempt)`.
Replace this with `retry_engine.plan_next_attempt(attempt, reviewer_feedback)` which
returns `(should_retry: bool, modified_content: str, modified_config: dict)`.

---

### Project 2 — Code Execution Sandbox (Validate What You Generate)

**Current state:**

The pipeline generates code but never runs it. `ExecutionEngine` in
`app/execution/engine.py` is named "Execution" but it executes workflow stages (LLM
calls), not code. `SafetyPolicy` validates that files are written within the workspace
boundary — it does not validate that the code compiles or passes tests.

`SprintDeploy` stage writes files. `QA` stage generates a test report. But neither
actually executes the generated tests. The QA artifact is a textual document produced
by an LLM, not a result from running `pytest`. This means QA can report "all tests pass"
on code that doesn't compile.

**The design:**

A `CodeSandbox` component that wraps a Docker container (or subprocess for simple cases)
and provides three operations:

```python
class CodeSandbox:
    def lint(self, project_id: str) -> LintResult:
        """Run ruff/eslint on generated files. Returns list of errors with line numbers."""

    def test(self, project_id: str) -> TestResult:
        """Run pytest/jest on generated tests. Returns pass/fail with stdout."""

    def build(self, project_id: str) -> BuildResult:
        """Attempt to build/bundle the project. Returns success + any compile errors."""
```

These run against `temp-workspace/{project_id}/project/` after each SprintDeploy.
Results feed directly back to BugAnalyst:

```
SprintDeploy writes files
  → CodeSandbox.lint()  → LintResult
  → CodeSandbox.test()  → TestResult
  → BugAnalyst receives (LintResult + TestResult) as structured input
  → BugAnalyst produces actual bug report from real errors, not hallucinated tests
  → BackendDeveloper/FrontendDeveloper receive bug report → fix real issues
```

**How it differs:** Today QA is an LLM that imagines what tests would say. With the
sandbox, QA receives real `pytest` output: `FAILED test_auth.py::test_login - AssertionError`.
The model can fix a real error. It cannot fix an imagined one. This is the single change
that converts AI DevOS from "generates code" to "generates working code."

**Infrastructure:** Docker image per language stack, pre-warmed. Python projects use
`python:3.12-slim` + `pytest`. Node projects use `node:20-slim` + `jest`. The sandbox
has no network access (security boundary). Execution timeout: 60s per operation.

---

### Project 3 — Project Intelligence Layer (Activate What's Already Built)

**Current state:**

`FileIndexer`, `ProjectDependencyGraph`, `CodeSummarizer`, and `ContextOrchestrator`
all exist in `app/intelligence/`. They are wired in `container.py` and registered as
singletons. In `WorkflowEngine._with_intelligence_context()`:

```python
if self.context_orchestrator is None:
    return content  # always takes this branch in practice
```

The intelligence layer contributes zero to any prompt today. It has no write path — nothing
calls `FileIndexer.index()` after `SprintDeploy` writes files.

**The design:**

Two changes activate the intelligence layer: a write trigger and a validated read path.

**Write trigger** (after every SprintDeploy):
```python
# In PipelineSupervisor, after SprintDeploy stage approval:
self.file_indexer.index(project_id, workspace_path)
self.dependency_graph.build(project_id, workspace_path)
self.code_summarizer.summarize(project_id, workspace_path)
```

**Validated read path** (in MemoryOrchestrator.get_context()):
```python
try:
    intelligence = self.context_orchestrator.get_project_state(project_id)
except Exception as exc:
    logger.warning("intelligence layer failed: %s — continuing without it", exc)
    intelligence = None
# Never silently None — always attempted, failure is logged
```

Once active, the intelligence layer gives code-generation stages real structural
knowledge. When BackendDeveloper runs for Sprint 3, it knows:
- Which modules already exist and what they export
- Which functions are called but not yet defined (dependency graph gaps)
- What the auth module's interface looks like (code summary)

**How it differs:** Currently `BackendDeveloper` in Sprint 3 has no knowledge of what
was generated in Sprints 1 and 2 unless those artifacts are explicitly passed in context.
The intelligence layer gives it live structural awareness of the codebase as it grows.
This eliminates entire classes of bugs: duplicate function definitions, wrong import paths,
calling non-existent APIs across module boundaries.

---

### Project 4 — Template Engine (Cross-Project Acceleration)

**Current state:**

`LearningLoop` stores cross-project patterns as strings matched by keyword similarity.
`LessonStore` stores what worked/failed per stage per project. `KnowledgeBase` stores
vectorized content. None of these have a write path from stage approvals — they must be
called explicitly, and they aren't. Cross-project learning is implemented but dead.

**The design:**

A `TemplateEngine` that treats completed, successful projects as reusable blueprints:

```python
class TemplateEngine:
    def extract_template(self, project_id: str) -> ProjectTemplate:
        """Called after Retro stage. Extracts reusable components from a completed project."""
        # Architecture pattern: what kind of stack was chosen and why
        # Sprint structure: how many sprints, what was in each
        # File structure: directory layout that worked
        # Lessons: what the Reviewer rejected and what fixed it

    def find_similar(self, request: str, top_k: int = 3) -> list[ProjectTemplate]:
        """Semantic search over templates for the new project's request."""

    def inject_template(self, context: StageContext, template: ProjectTemplate) -> StageContext:
        """Add matched template's architecture/sprint patterns to the stage context."""
```

When a new project "build a todo app" starts, `TemplateEngine.find_similar()` returns
the last three successful todo/task-management projects. Their architecture decisions,
sprint breakdowns, and file structures are injected into Architect's context as examples.

**Three template types:**

*Architecture templates* — "React + FastAPI + PostgreSQL for a user-facing CRUD app
with auth." Injected into Architect stage. Reduces hallucinated architectures.

*Sprint templates* — "Sprint 1: models + schemas. Sprint 2: API routes. Sprint 3: auth.
Sprint 4: frontend." Injected into SprintPlanner. Produces realistic sprint plans instead
of AI-fantasy sprint breakdowns.

*Prompt templates* — Stage prompts that historically produced high-quality outputs,
extracted and versioned by `AgentPerformanceScorer`. When a stage is scoring below 0.70,
the TemplateEngine replaces its prompt with the historically best-performing version.

**How it differs:** Currently every project starts from zero. The system has run the same
"calculator app" concept multiple times (we can see it in the artifacts) and produced
different architectures each time. The Template Engine makes the 10th calculator app
significantly better than the first, because the first nine's decisions are available
as structured examples. This is the difference between a junior developer and a senior
one — same tools, but years of similar decisions to draw from.

---

### Project 5 — Human-in-the-Loop Collaboration Gates

**Current state:**

The only interactive point is the Q&A clarification phase at the start. After that, the
pipeline runs entirely autonomously. There is no way for a human to redirect mid-pipeline
without stopping the entire run. The `design_review` field exists in `project.json` with
a `pending` status but there is no corresponding API endpoint that pauses the pipeline
waiting for feedback.

```json
"design_review": {
    "status": "pending",
    "user_feedback": null,
    "iteration": 0
}
```

**The design:**

Three structured collaboration gates, each pausing the pipeline and waiting for human
approval before continuing:

**Gate 1 — Architecture Review** (after Architect stage, before Designer)
The pipeline sends the approved `ArchitectureArtifact` to the user: stack choices, module
breakdown, database schema decisions. The user can approve, request changes, or override.
Pipeline is paused with state `ARCHITECTURE_REVIEW_PENDING`. This prevents the entire
codebase from being generated on an architecture the user rejects in retrospect.

**Gate 2 — Design Review** (after Designer stage, before Security)
The `DesignArtifact` (UI components, layouts, color system) is surfaced for user approval.
`design_review` already exists in `project.json` — this activates it. The user can say
"make it dark mode" or "add a sidebar" before Security and SprintPlanner lock in the
scope.

**Gate 3 — Sprint Plan Review** (after SprintPlanner, before ScrumMaster)
The generated sprint breakdown is surfaced: "6 sprints, 4 files per sprint, estimated
120 LLM calls." The user approves or adjusts scope (drop sprints, merge files) before
the most expensive phase begins. This is where cost control is most impactful — a user
can kill a 20-sprint plan before spending $40.

**How it differs:** Currently the system makes all architectural decisions autonomously
and shows them to the user only after code is generated. The gates surface decisions at
the point where changing them is still cheap. A wrong architecture discovered at the
Architecture Review gate costs 0 tokens to fix. The same discovery after Sprint 4 costs
4 sprints × N files × M tokens to regenerate.

**API pattern:**
```
POST /workflow/{id}/architecture/approve     → continue to Designer
POST /workflow/{id}/architecture/revise      → body: {feedback: "..."} → re-run Architect with feedback
POST /workflow/{id}/sprint-plan/approve      → continue to ScrumMaster
POST /workflow/{id}/sprint-plan/adjust       → body: {max_sprints: 4} → re-plan within constraint
```

---

### Project 6 — Multi-Model Stage Routing

**Current state:**

`LLM_PROVIDER` and `LLM_MODEL` in `.env` apply globally to every stage. DomainResearch
(a research task), ProductOwner (a structured JSON generation task), and BackendDeveloper
(a code generation task) all use the same model with the same temperature and token limits.
These are fundamentally different tasks with different optimal models.

**The design:**

A `ModelRouter` that selects the optimal provider and model per stage based on task type:

```python
STAGE_MODEL_PROFILE: dict[str, ModelProfile] = {
    # Research tasks: need broad knowledge, web access preferred
    "DomainResearch":     ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                        temperature=0.3, max_tokens=4096),

    # Structured JSON generation: need precision, low hallucination
    "ProductOwner":       ModelProfile(provider="claude", model="claude-sonnet-4-6",
                                        temperature=0.1, max_tokens=16384),
    "Architect":          ModelProfile(provider="claude", model="claude-sonnet-4-6",
                                        temperature=0.1, max_tokens=8192),

    # Creative/design tasks: need variation, higher temperature ok
    "Designer":           ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                        temperature=0.5, max_tokens=4096),

    # Code generation: need specialized code model
    "BackendDeveloper":   ModelProfile(provider="bedrock", model="qwen.qwen3-vl-235b-a22b",
                                        temperature=0.05, max_tokens=32768),
    "FrontendDeveloper":  ModelProfile(provider="bedrock", model="qwen.qwen3-vl-235b-a22b",
                                        temperature=0.05, max_tokens=32768),

    # Review/analysis: cheap model is sufficient
    "BugAnalyst":         ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                        temperature=0.2, max_tokens=4096),
    "Document":           ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                        temperature=0.3, max_tokens=4096),
}
```

Env vars act as overrides: `STAGE_PRODUCTOWNER_MODEL=claude-opus-5` overrides just
ProductOwner's model without changing anything else.

**Cost impact:** Research/review stages (DomainResearch, BugAnalyst, Document, Retro)
can use cheap fast models. Precision stages (ProductOwner, Architect) use high-quality
models. Code stages (BackendDeveloper, FrontendDeveloper) use code-specialized models.
Routing eliminates the need to pay for expensive models on tasks that don't need them.

**Performance impact:** DomainResearch with `gemini-2.0-flash` returns in ~2 seconds.
The same with `claude-sonnet-4-6` returns in ~8 seconds. For a 19-stage pipeline, routing
to the fastest sufficient model per stage reduces total wall-clock time by 40–60%.

**How it differs:** Today all stages use one model chosen before the pipeline starts.
Model routing makes the LLM selection part of the pipeline configuration, not a global
setting. The pipeline becomes adaptive: it uses the right tool for each job.

---

### Comparison: Current System vs. Six Projects

| Dimension | Current | With All Six Projects |
|---|---|---|
| Retry quality | Identical prompt each time | Each retry addresses specific failure cause |
| Code validity | LLM claims tests pass | Sandbox actually runs tests |
| Cross-sprint awareness | None (each sprint is blind) | Intelligence layer tracks symbols/dependencies |
| Cross-project learning | Dead code paths | Templates from every successful project |
| User control | QA only, then autonomous | 3 structured gates at decision points |
| Model selection | One global model | Per-stage routing to optimal model |
| Cost per project | ~$2–$3 (all stages, expensive model) | ~$0.60–$1.20 (routing + fewer retries) |
| Code correctness rate | Unknown (never tested) | Measurable (sandbox pass rate) |
| Pipeline speed | ~45–90 min per project | ~20–40 min (fast models for cheap stages) |

### Implementation Priority

The six projects are not equal in impact. Order of priority:

**Do first (unblocks everything else):**
- Project 1 (Intelligent Retry) — fixes the ProductOwner failure loop immediately
- Project 3 (Intelligence Layer) — 90% built, needs a write trigger and a validated read

**Do second (major capability jumps):**
- Project 2 (Code Sandbox) — converts "generates code" to "generates working code"
- Project 5 (Collaboration Gates) — adds cost control at the most impactful point

**Do third (acceleration and quality):**
- Project 4 (Template Engine) — requires completed projects to learn from
- Project 6 (Model Routing) — requires stable pipeline first

---

## 10. Quick Win Summary (Do This Week)

If you want the pipeline to run reliably with Bedrock right now, before the larger fixes:

```
1. Fix Bug A: in manager.py else-branch, save minimal Clarification artifact before
   calling _pipeline_supervisor.run() — this is the primary pipeline blocker

2. Fix Bug B: in engine.py _with_clarification_context(), replace the clarification={}
   fallback with a structured dict built from project.json's original_request

3. Change workflow:latest_message → workflow:stage:{stage_name} in engine.py
   (grep -r "workflow:latest_message" backend/ to find all write/read sites)

4. Set LLM_MAX_TOKENS=16384 in .env — gives models room for large RequirementsArtifact

5. Add LOG_LEVEL=DEBUG in .env — see exactly what context each agent receives

6. After Bug A+B are fixed, add the SprintDeploy write trigger for FileIndexer/
   DependencyGraph — the intelligence layer needs one line to activate
```

The system is architecturally sound in its intentions. The gaps are mostly operational
maturity, not fundamental design mistakes. It is 6–8 weeks of focused engineering away
from being genuinely production-ready for a small team's internal use (5–20 projects/day).
For public multi-tenant SaaS, add 3–4 more months for auth, PostgreSQL, S3, and observability.

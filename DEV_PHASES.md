# AI DevOS — Development Phases

> Derived from STRATEGY.md full analysis. This document is the implementation
> contract: what to remove, what to update, what to build new, and in what order.
> Every decision is traceable to a root cause in STRATEGY.md.

---

## How to Read This Document

Each phase is self-contained and shippable. Complete Phase 1 before starting Phase 2.
Each item follows this format:

```
ACTION   FILE(s)                    WHAT                          WHY
──────────────────────────────────────────────────────────────────────
REMOVE   workflow/engine.py         _with_clarification_context   replaced by MemoryOrchestrator
UPDATE   workflow/manager.py        _handle_clarifying_state      Bug A fix
NEW      memory/orchestrator.py     MemoryOrchestrator class      unified context layer
```

**Actions defined:**
- `REMOVE` — delete this code. It is replaced by something better.
- `UPDATE` — modify this file. Description says exactly what changes.
- `NEW` — create this file/class. Did not exist before.
- `ACTIVATE` — code exists but is disabled. Wire it in and validate.
- `MIGRATE` — move code from one location to another without changing behavior.
- `DEPRECATE` — mark as deprecated now; remove in the next phase.

---

## Phase 0 — Unblock the Pipeline (2–3 days)

**Goal:** Make a single project run end-to-end with Bedrock without manual intervention.
Nothing architectural. Two targeted bug fixes and one config change.

### What to Update

```
UPDATE   backend/app/workflow/manager.py
         Method: _handle_clarifying_state()
         Location: the else-branch around line 312 (when questions == [])

         Before: else-branch calls _run_stage("StrategicReview") → _pipeline_supervisor.run()
                 with no Clarification artifact saved

         After:  before calling _pipeline_supervisor.run(), save a minimal
                 Clarification artifact built from original_request:
                 {
                     "original_request": request,
                     "project_description": request,
                     "functional_requirements": [],
                     "non_functional_requirements": [],
                     "scale_profile": {
                         "user_count": "unknown",
                         "auth_needed": False,
                         "database_needed": False,
                         "infrastructure_tier": "unknown"
                     },
                     "inferred_scope": "QA bypassed — infer scope from original request"
                 }
                 Then log a warning so the bypass is visible.

         Why:    Bug A — pipeline bypasses QA silently, never writes Clarification.json.
                 ProductOwner receives clarification:{} and produces requirements:[].
                 Reviewer rejects. Pipeline exhausts retries. Stage fails.
```

```
UPDATE   backend/app/workflow/engine.py
         Method: _with_clarification_context()
         Location: the None-check after get_artifact() call

         Before: if clarification_artifact is None → clarification_struct = {}

         After:  if clarification_artifact is None:
                     load project.json via workspace_manager.load_project_json(project_id)
                     build clarification_struct = {
                         "original_request": p_data.get("original_request") or content,
                         "project_description": p_data.get("description") or content,
                         "inferred_scope": "No clarification performed. Infer scope.",
                         "functional_requirements": [],
                         "scale_profile": {"user_count": "unknown", "auth_needed": False}
                     }
                     log a warning naming the project_id

         Why:    Bug B — defense in depth. Even if Bug A is fixed, any future QA bypass
                 path must not send {} to ProductOwner. The fallback makes the system
                 resilient to any upstream failure in the QA flow.
```

```
UPDATE   backend/.env
         Add: LLM_MAX_TOKENS=16384
         Add: LLM_TEMPERATURE=0.1

         Why:    RequirementsArtifact JSON with full requirements, user_stories,
                 acceptance_criteria, goals, success_metrics, constraints needs
                 8000–12000 tokens. Default 4096 causes truncated output → empty fields.
```

### Verification Checkpoint

After Phase 0, create a new project via API and confirm:
- `artifacts/Clarification.json` exists in temp-workspace after QA phase
- `ProductOwner.json` has non-empty `requirements` array
- Pipeline reaches Architect stage without manual intervention

---

## Phase 1 — Memory Foundation (1–2 weeks)

**Goal:** Replace the fragile single-slot predecessor memory with per-stage persistent
storage. This is the foundational change that makes all future context work correct.

### What to Remove

```
REMOVE   backend/app/workflow/engine.py
         Constant: _WORKFLOW_MESSAGE_KEY = "workflow:latest_message"
         All reads: memory_manager.load(project_id, _WORKFLOW_MESSAGE_KEY)
         All writes: memory_manager.store(project_id, _WORKFLOW_MESSAGE_KEY, ...)

         Replace with: memory_manager.store/load using "workflow:stage:{stage_name}"
         Why: Single slot overwrites on every stage. Stage N has no access to Stage N-3.
              Root cause of the entire context assembly problem class.
```

```
REMOVE   backend/app/workflow/engine.py
         Methods (after MemoryOrchestrator is built and wired):
         - _with_predecessor_message()
         - _with_clarification_context()
         - _with_design_context()
         - _with_relevant_patterns()
         - _with_lessons()
         - _with_intelligence_context()

         Replace with: single call to memory_orchestrator.get_context(project_id, stage)
         Why: Six ad-hoc enrichment methods with no shared contract. Every new stage
              needing non-adjacent data requires a new method. Not scalable.

         IMPORTANT: Do NOT remove these until MemoryOrchestrator is fully built
                    and validated in staging. Remove them in the same PR that
                    wires in MemoryOrchestrator.get_context().
```

### What to Update

```
UPDATE   backend/app/workflow/engine.py
         Method: run()
         
         Replace the current enrichment chain:
             base_content = self._with_predecessor_message(...)
             base_content = self._with_clarification_context(...)
             base_content = self._with_design_context(...)
             base_content = self._with_relevant_patterns(...)
             base_content = self._with_lessons(...)
             base_content = self._with_intelligence_context(...)
         
         With:
             context = self.memory_orchestrator.get_context(project_id, Stage(stage_name))
             prompt = agent.build_prompt(context)

         Also update the approval recording:
             # After stage is approved:
             self.memory_orchestrator.record_approval(project_id, stage, result.artifact)
             # After stage is rejected:
             self.memory_orchestrator.record_rejection(project_id, stage, feedback)

         Why: Centralize all context assembly. One method call instead of six.
```

```
UPDATE   backend/app/memory/manager.py
         Add two new methods alongside existing store/load:

         store_stage_output(project_id: str, stage_name: str, content: str) → None
             key = f"workflow:stage:{stage_name}"
             delegates to existing store()

         load_stage_output(project_id: str, stage_name: str) -> str | None
             key = f"workflow:stage:{stage_name}"
             delegates to existing load()

         Why: Named accessors prevent key string typos. Existing store/load
              infrastructure is reused — no schema change needed.
```

```
UPDATE   backend/app/workflow/manager.py
         Method: _handle_qa_flow() — Phase B (synthesize answers)
         After: self.artifact_manager.save_artifact(Stage.Clarification, ...)
         Add:   self.memory_manager.store_stage_output(project_id, "Clarification",
                    json.dumps(clarification_struct))

         Method: _run_stage() — after every stage approval
         Add:   self.memory_manager.store_stage_output(project_id, stage_name,
                    approved_content)

         Why: Every approved stage output must be independently retrievable.
              The artifact file system is the durable store; memory is the fast-access layer.
```

### What to Build New

```
NEW      backend/app/memory/orchestrator.py
         Class: MemoryOrchestrator

         Public interface:
             __init__(memory_manager, artifact_manager, workspace_manager,
                      learning_loop, lesson_store, context_orchestrator)

             get_context(project_id: str, stage: Stage) → StageContext
                 Assembles all four memory layers into one typed object:
                 - Layer 1 (Working): reads per-stage memory keys for declared dependencies
                 - Layer 2 (Episodic): reads artifact files for typed structured content
                 - Layer 3 (Semantic): reads learning_loop patterns + lesson_store lessons
                 - Layer 4 (Procedural): calls context_orchestrator.get_project_state()
                 Returns StageContext dataclass (see NEW StageContext below)

             record_approval(project_id: str, stage: Stage, artifact: dict) → None
                 Writes to:
                 - memory_manager.store_stage_output() (fast access)
                 - artifact_manager (already handled by WorkflowEngine — don't duplicate)
                 Schedules async: learning_loop.record_success(stage, artifact)

             record_rejection(project_id: str, stage: Stage, feedback: ReviewFeedback) → None
                 Writes to:
                 - memory_manager (attempt log)
                 Schedules async: lesson_store.record(stage, feedback)

         Error contract:
             get_context() NEVER raises. If any layer fails, it logs a warning
             and returns the best available context with the failed layer empty.
             record_*() failures are logged but do not propagate to the caller.

         Why: Replaces six _with_* methods. Single responsibility: assemble context.
```

```
NEW      backend/app/shared/dto/stage_context.py
         Dataclass: StageContext

         Fields:
             project_id: str
             stage: Stage
             original_request: str
             predecessor_outputs: dict[str, Any]     # {"Clarification": {...}, "StrategicReview": {...}}
             clarification: ClarificationArtifact | None
             strategic_brief: dict | None
             domain_research: dict | None
             design_artifact: dict | None
             architecture_artifact: dict | None
             lessons: list[str]
             patterns: list[str]
             intelligence: dict | None               # from ProjectIntelligence layer
             token_budget: int
             assembled_at: datetime

         Why: Typed context replaces untyped string content. Prompt builders receive
              this object and access named fields. No string parsing, no Path A/B/C.
```

```
NEW      backend/app/kernel/health_check.py
         Function: validate_container(container) → list[str]
             Iterates all registered singleton names.
             For each: assert container.resolve(name) is not None
             Returns list of failed names.
             Called at startup by kernel.py — if any fail, log ERROR but continue.

         Why: Currently container.resolve("lesson_store") is wrapped in try/except
              because it might not be registered. Silent None singletons cause
              AttributeError at runtime, not at startup.
```

### What to Activate

```
ACTIVATE backend/app/context/context.py
         Class: ContextManager (exists, wired in container but bypassed)

         Current state: container.py creates ContextManager but WorkflowEngine
                        never calls it — all enrichment is done inline via _with_* methods.

         Action: MemoryOrchestrator delegates to ContextManager for Layer 3 (Semantic)
                 assembly. ContextManager.build_context() already reads LearningLoop
                 and LessonStore — this is exactly Layer 3.

         Why: ContextManager is fully implemented and correct. It just has no caller.
              Activating it via MemoryOrchestrator gives it a defined role.
```

### Verification Checkpoint

After Phase 1:
- `grep -r "workflow:latest_message" backend/` returns zero results
- `grep -r "_with_clarification_context\|_with_predecessor_message\|_with_design_context" backend/` returns zero results  
- All 19 stages retrieve context via `memory_orchestrator.get_context()`
- `ProductOwner.json` structured content includes non-empty `clarification` field on every run

---

## Phase 2 — Intelligent Retry + Quality Scoring (1 week)

**Goal:** Make retries meaningful. Each retry should address the specific reason the
previous attempt failed, not blindly repeat it.

### What to Remove

```
REMOVE   backend/app/workflow/retry_policy.py
         Class: RetryPolicy (the entire file)

         Current code:
             def should_retry(self, attempt: int) -> bool:
                 return attempt < self.max_retries

         Replace with: IntelligentRetryEngine (see NEW below)
         Why: One-liner policy with no access to rejection reason. Cannot improve.
```

### What to Update

```
UPDATE   backend/app/workflow/engine.py
         Method: run() — the retry loop

         Before:
             while retry_policy.should_retry(attempt):
                 result = execute(...)
                 review = reviewer.review(result)
                 if review.approved: break
                 attempt += 1

         After:
             while True:
                 result = execute(...)
                 review = reviewer.review(result)
                 if review.approved: break
                 retry_plan = retry_engine.plan(attempt, review.feedback, stage_name)
                 if not retry_plan.should_retry: break
                 content = retry_plan.modified_content   # enriched prompt for next attempt
                 llm_config = retry_plan.modified_config  # e.g. higher max_tokens
                 attempt += 1

         Why: Retry strategy is now driven by rejection type, not just attempt count.
```

```
UPDATE   backend/app/learning/performance_scorer.py
         Class: AgentPerformanceScorer
         Method: score_agent()

         Add: score is written to memory_manager on every call:
              memory_manager.store(project_id, f"perf:{stage}", json.dumps(score))

         Add: score feeds into retry_engine:
              If score.quality == "needs_improvement" AND avg_retries > 1.5:
                  flag stage for model escalation on next retry

         Why: AgentPerformanceScorer currently produces scores that nothing reads.
              Wiring it to retry_engine gives it a real effect.
```

### What to Build New

```
NEW      backend/app/workflow/retry_engine.py
         Class: IntelligentRetryEngine

         Method: plan(attempt: int, feedback: ReviewFeedback, stage: str) → RetryPlan

         RetryPlan fields:
             should_retry: bool
             modified_content: str       # content to send on next attempt
             modified_config: dict       # {"max_tokens": 16384, "temperature": 0.05}
             strategy: str               # "schema_injection" | "context_rebuild" | "escalate"
             reason: str                 # human-readable explanation

         Strategy map (what triggers what):
             feedback.type == "empty_required_field"
                 → inject field-specific reminder: "You MUST populate the {field} array"
                 → increase max_tokens by 50% in modified_config
                 → strategy = "field_reminder"

             feedback.type == "schema_mismatch"
                 → inject exact schema with example JSON from schema_model.__doc__
                 → set temperature=0.05 in modified_config
                 → strategy = "schema_injection"

             feedback.type == "ask_human" AND stage in CRITICAL_SCHEMAS
                 → should_retry = False (escalate immediately, retrying won't help)
                 → strategy = "escalate"

             feedback.type == "low_quality"
                 → pull latest lesson from lesson_store for this stage
                 → prepend lesson to content
                 → strategy = "lesson_injection"

             feedback.type == "token_truncated"
                 → reduce input context length by 30% (trim lessons/patterns section)
                 → increase max_tokens by 100%
                 → strategy = "token_rebalance"

             attempt >= max_retries
                 → should_retry = False regardless of type

         Why: Replaces RetryPolicy's blind counter with a diagnostic decision tree.
              Each retry is meaningfully different from the last.
```

```
NEW      backend/app/shared/dto/retry_plan.py
         Dataclass: RetryPlan
             should_retry: bool
             modified_content: str
             modified_config: dict
             strategy: str
             reason: str

         Why: Typed return from IntelligentRetryEngine. Engine and caller
              are decoupled — caller only reads the plan, not the strategy logic.
```

### Verification Checkpoint

After Phase 2:
- A stage that fails with `empty_required_field` on attempt 1 has a different prompt on attempt 2 (check logs)
- A stage that fails with `ask_human` on a critical schema does NOT retry — pipeline escalates immediately
- `AgentPerformanceScorer.score_agent("ProductOwner")` returns non-None score after one project run

---

## Phase 3 — Activate Intelligence Layer (1 week)

**Goal:** Make `FileIndexer`, `DependencyGraph`, and `CodeSummarizer` contribute to
code-generation stages. They are built; they need a write trigger and a read path.

### What to Update

```
UPDATE   backend/app/workflow/pipeline_supervisor.py
         Method: _run_sprint() or equivalent (the method that calls SprintDeploy)

         After SprintDeploy stage is approved, add:
             workspace_path = self.workspace_manager.get_project_path(project_id)
             try:
                 self.file_indexer.index(project_id, workspace_path)
                 self.dependency_graph.build(project_id, workspace_path)
                 self.code_summarizer.summarize(project_id, workspace_path)
                 logger.info("intelligence layer updated: project_id=%s", project_id)
             except Exception as exc:
                 logger.warning("intelligence layer update failed: %s — continuing", exc)

         Why: Currently nothing calls index/build/summarize after files are written.
              The intelligence layer has no data to serve. This is the missing write trigger.
```

```
UPDATE   backend/app/intelligence/context_orchestrator.py
         Method: get_project_state() (or equivalent query method)

         Remove: any guard that returns early when index is empty
         Replace with: return available data + metadata about completeness:
             {
                 "files": [...],                    # empty list if not indexed yet
                 "symbols": [...],
                 "dependencies": [...],
                 "summaries": {...},
                 "indexed_at": "...",
                 "is_populated": bool               # False on first sprint, True after
             }

         Why: Current guard prevents the layer from being used on Sprint 1 (correct)
              but also silently disables it forever when it returns None (incorrect).
              A structured empty response is better than None.
```

```
UPDATE   backend/app/memory/orchestrator.py  (NEW from Phase 1)
         Method: get_context() — Layer 4 assembly

         Replace:
             if self.context_orchestrator is None: return None

         With:
             try:
                 intelligence = self.context_orchestrator.get_project_state(project_id)
             except Exception as exc:
                 logger.warning("procedural memory failed for %s: %s", project_id, exc)
                 intelligence = None
             # intelligence is set in StageContext whether populated or None
             # Stages that need it check context.intelligence.is_populated

         Why: Silent None means the layer never contributes. Logged failure + structured
              empty means the layer is attempted on every stage and contributes when ready.
```

```
UPDATE   backend/app/kernel/container.py
         FileIndexer, DependencyGraph, CodeSummarizer, ContextOrchestrator singletons:

         Remove: any try/except that swallows construction errors silently
         Add:    after each construction, assert the object is not None and log its status
         Add:    pass all four to MemoryOrchestrator constructor (not just ContextOrchestrator)

         Why: Currently ContextOrchestrator may be None because lesson_store resolution
              fails in a try/except. The intelligence layer is then permanently disabled
              for the entire process lifetime.
```

### What to Activate

```
ACTIVATE backend/app/intelligence/file_indexer.py
         Trigger: SprintDeploy stage approval (see UPDATE to pipeline_supervisor.py above)
         Input:   workspace path of the project being built
         Output:  symbol index stored in file_index.db per project_id

ACTIVATE backend/app/intelligence/dependency_graph.py
         Trigger: same as FileIndexer (called together)
         Input:   workspace path
         Output:  import/dependency map stored per project_id

ACTIVATE backend/app/intelligence/code_summarizer.py
         Trigger: same as above
         Input:   workspace path + file index
         Output:  per-file summaries stored per project_id

         Why for all three: these are the most valuable context enrichment for
         BackendDeveloper and FrontendDeveloper in Sprint 2+. Without them,
         Sprint 3 BackendDeveloper has no knowledge of what Sprint 1 produced.
```

### Verification Checkpoint

After Phase 3:
- After a project's first sprint completes, `file_index.db` contains entries for that project
- BackendDeveloper in Sprint 2 receives `context.intelligence.summaries` with Sprint 1 file summaries
- `GET /api/v1/intelligence/{project_id}` returns non-empty response after first sprint

---

## Phase 4 — Human Collaboration Gates (1–2 weeks)

**Goal:** Add three structured pause points where a human can review and approve before
expensive pipeline phases run.

### What to Update

```
UPDATE   backend/app/shared/enums/project_state.py
         Add three new states:
             ARCHITECTURE_REVIEW_PENDING = "architecture_review_pending"
             DESIGN_REVIEW_PENDING = "design_review_pending"       # already exists — verify
             SPRINT_PLAN_REVIEW_PENDING = "sprint_plan_review_pending"

         Why: Pipeline needs to pause at each gate. States make the pause explicit
              and resumable across server restarts.
```

```
UPDATE   backend/app/workflow/pipeline_supervisor.py
         After Architect stage approval:
             self._transition(project_id, ProjectState.ARCHITECTURE_REVIEW_PENDING)
             self.broadcaster.status_update(project_id, "architecture_review_pending", ...)
             return PipelineResult(requires_user_action=True, action_needed="review_architecture")
             # Pipeline stops here — resumes when POST /workflow/{id}/architecture/approve

         After Designer stage approval:
             self._transition(project_id, ProjectState.DESIGN_REVIEW_PENDING)
             return PipelineResult(requires_user_action=True, action_needed="review_design")

         After SprintPlanner stage approval:
             self._transition(project_id, ProjectState.SPRINT_PLAN_REVIEW_PENDING)
             broadcaster: include estimated cost in the status update
             return PipelineResult(requires_user_action=True, action_needed="review_sprint_plan")

         Why: Currently these stages run autonomously back-to-back. Architect can choose
              a wrong stack and the user sees it only after 20 sprint files are generated.
```

```
UPDATE   backend/app/workflow/manager.py
         Method: run()
         Add state handlers alongside existing QA_PENDING / QA_IN_PROGRESS handlers:

             if state == ProjectState.ARCHITECTURE_REVIEW_PENDING:
                 return self._await_gate(project_id, "architecture")
             if state == ProjectState.DESIGN_REVIEW_PENDING:
                 return self._await_gate(project_id, "design")
             if state == ProjectState.SPRINT_PLAN_REVIEW_PENDING:
                 return self._await_gate(project_id, "sprint_plan")

         Why: Manager's run() is the state machine entry point. New states need handlers.
```

### What to Build New

```
NEW      backend/app/api/gates.py
         FastAPI router: /workflow/{project_id}/gates/

         POST /workflow/{project_id}/gates/architecture/approve
             body: {} (no payload — approve as-is)
             action: transition to DESIGNING, resume pipeline
             response: {"status": "resumed", "next_stage": "Designer"}

         POST /workflow/{project_id}/gates/architecture/revise
             body: {"feedback": "Use PostgreSQL not SQLite, add Redis for caching"}
             action: store feedback in memory, re-run Architect with feedback injected
             response: {"status": "revision_requested"}

         POST /workflow/{project_id}/gates/design/approve
             action: transition to SECURITY state, resume pipeline

         POST /workflow/{project_id}/gates/design/revise
             body: {"feedback": "Dark mode, add sidebar navigation"}
             action: re-run Designer with feedback

         POST /workflow/{project_id}/gates/sprint-plan/approve
             action: transition to sprint execution

         POST /workflow/{project_id}/gates/sprint-plan/adjust
             body: {"max_sprints": 4, "feedback": "Drop the analytics sprint"}
             action: re-run SprintPlanner with constraint injected

         GET /workflow/{project_id}/gates/current
             response: {"gate": "architecture_review_pending", "artifact": {...}}
             Frontend uses this to know which gate is active and what to show

         Why: Gives the user structured control over pipeline direction at three points
              where course-correction is still cheap.
```

```
NEW      backend/app/shared/dto/gate_result.py
         Dataclass: GateResult
             gate_name: str          # "architecture" | "design" | "sprint_plan"
             action: str             # "approved" | "revision_requested" | "adjusted"
             feedback: str | None
             constraint: dict | None

         Why: Typed return from gate endpoints. Supervisor reads this to decide
              whether to continue or re-run the preceding stage.
```

### Verification Checkpoint

After Phase 4:
- Pipeline pauses after Architect with state `architecture_review_pending`
- `GET /workflow/{id}/gates/current` returns the ArchitectureArtifact JSON
- `POST /workflow/{id}/gates/architecture/approve` resumes pipeline at Designer
- `POST /workflow/{id}/gates/sprint-plan/adjust` with `max_sprints=3` produces a 3-sprint plan

---

## Phase 5 — Code Execution Sandbox (2–3 weeks)

**Goal:** Run generated code in a sandbox and feed real test results to BugAnalyst.
This converts the system from "generates code" to "generates code that executes."

### What to Update

```
UPDATE   backend/app/agents/factory.py
         BugAnalyst agent construction:

         Before: BugAnalyst receives LLM-generated QA report as its input
         After:  BugAnalyst receives: {
                     "qa_report": <LLM QA artifact>,
                     "sandbox_results": {
                         "lint": LintResult,
                         "test": TestResult,
                         "build": BuildResult
                     }
                 }

         Why: BugAnalyst should analyze real errors, not imagined ones.
              Lint errors have line numbers. Test failures have stack traces.
              These are far more actionable than a hallucinated test description.
```

```
UPDATE   backend/app/workflow/pipeline_supervisor.py
         After SprintDeploy stage approval (same location as intelligence layer trigger):

         sandbox_results = self.code_sandbox.run(project_id)
         broadcaster.log_line(project_id, "Sandbox",
             f"Lint: {sandbox_results.lint.error_count} errors | "
             f"Tests: {sandbox_results.test.passed}/{sandbox_results.test.total} | "
             f"Build: {'OK' if sandbox_results.build.success else 'FAILED'}")

         # Store results for BugAnalyst
         memory_manager.store(project_id, "sandbox:latest", sandbox_results.to_json())

         Why: Sandbox results are available before BugAnalyst runs.
              BugAnalyst then reads real results instead of imagining them.
```

```
UPDATE   backend/app/execution/safety_policy.py
         Add: sandbox execution is considered a read-only operation on project files
         All sandbox commands run with no-network flag in Docker
         Timeout: 60 seconds per operation (lint, test, build)

         Why: Safety boundary must extend to sandbox. Generated code should not
              be able to make network calls, write outside project dir, or run indefinitely.
```

### What to Build New

```
NEW      backend/app/execution/sandbox.py
         Class: CodeSandbox

         __init__(workspace_manager, config: SandboxConfig)
             config: {
                 "docker_image_python": "python:3.12-slim",
                 "docker_image_node": "node:20-slim",
                 "timeout_seconds": 60,
                 "enabled": True   # can be disabled in .env for dev
             }

         detect_stack(project_id: str) → Literal["python", "node", "unknown"]
             Reads project files: if requirements.txt → python, if package.json → node

         lint(project_id: str) → LintResult
             Python: runs ruff check on project directory
             Node: runs eslint on project directory
             Returns: {errors: [{file, line, message}], error_count: int}

         test(project_id: str) → TestResult
             Python: runs pytest --tb=short --json-report
             Node: runs jest --json
             Returns: {passed: int, failed: int, total: int, failures: [{test_name, error}]}

         build(project_id: str) → BuildResult
             Python: python -c "import app" or equivalent import check
             Node: npm run build
             Returns: {success: bool, errors: [str]}

         run(project_id: str) → SandboxResult
             Calls lint() + test() + build() in sequence
             Stops on build failure (no point running tests if it doesn't import)
             Returns: SandboxResult aggregating all three

         Execution model:
             subprocess.run() with timeout for simple cases (dev mode, SANDBOX_ENABLED=false)
             docker run --network=none --read-only with volume mount for production

         Why: Generated code is never verified today. This is the single biggest
              quality improvement possible — real test results instead of hallucinated ones.
```

```
NEW      backend/app/shared/dto/sandbox_result.py
         Dataclasses:
             LintResult:  errors: list[dict], error_count: int, duration_ms: int
             TestResult:  passed: int, failed: int, total: int, failures: list[dict], duration_ms: int
             BuildResult: success: bool, errors: list[str], duration_ms: int
             SandboxResult: lint: LintResult, test: TestResult, build: BuildResult,
                            project_id: str, sprint: int, ran_at: datetime

         Why: Typed results give BugAnalyst structured input to analyze.
```

```
NEW      backend/.env additions
         SANDBOX_ENABLED=false      # default off until Docker is confirmed available
         SANDBOX_TIMEOUT=60
         SANDBOX_DOCKER_PYTHON=python:3.12-slim
         SANDBOX_DOCKER_NODE=node:20-slim

         Why: Sandbox requires Docker. In dev environments without Docker,
              disable it gracefully rather than crashing the pipeline.
```

### Verification Checkpoint

After Phase 5:
- After a sprint completes, `memory_manager.load(project_id, "sandbox:latest")` has lint/test/build results
- BugAnalyst artifact references real file paths and line numbers from lint errors
- If generated Python has a syntax error, `build.success = False` and the error message names the exact line
- `SANDBOX_ENABLED=false` in .env disables sandbox cleanly without affecting pipeline

---

## Phase 6 — Infrastructure & Production Hardening (3–4 weeks)

**Goal:** Make the system deployable, secure, and monitorable. No new features —
this phase makes what exists reliable at scale.

### What to Remove

```
REMOVE   backend/app/api/workflow.py
         Pattern: threading.Thread(target=_run_pipeline, daemon=True, ...)

         Replace with: Celery task queue (see NEW below)
         Why: daemon threads have no isolation, no cancellation, no backpressure.
              Two start requests for the same project_id create two competing threads.
```

```
REMOVE   backend/app/config/loader.py
         All hardcoded database path strings like "backend/app/memory/costs.db"

         Replace with: Path(__file__).parent.parent / "data" / "{name}.db" pattern
         Why: Relative paths break when uvicorn is started from a different directory.
              All 8 SQLite database paths have this bug.
```

### What to Update

```
UPDATE   backend/app/main.py
         Add FastAPI middleware (before route registration):
             - API key authentication middleware (reads X-API-Key header)
             - Rate limiting middleware (10 project creates per minute per key)
             - Request size limit (reject bodies > 50KB)
             - Structured logging middleware (adds project_id to every log line)

         Why: Currently zero authentication. Any HTTP client can create projects
              and consume Bedrock credits.
```

```
UPDATE   backend/app/api/project.py (or equivalent project creation endpoint)
         Add request validation:
             - description: max 2000 characters
             - name: max 100 characters, alphanumeric + spaces only
             - reject if project count for this API key exceeds MAX_PROJECTS_PER_KEY

         Why: 500,000-character descriptions get embedded in every LLM prompt.
              No validation = no cost control.
```

```
UPDATE   backend/requirements.txt
         Add:
             celery>=5.3.0
             redis>=5.0.0
             structlog>=24.0.0
             opentelemetry-sdk>=1.24.0
             opentelemetry-instrumentation-fastapi>=0.45b0
             prometheus-fastapi-instrumentator>=6.1.0

         Remove:
             pyyaml  (already optional — make removal explicit in requirements)

         Why: These are the infrastructure packages for the Phase 6 additions.
```

### What to Build New

```
NEW      backend/app/tasks/pipeline_task.py
         Celery task: run_pipeline

         @celery_app.task(bind=True, max_retries=0, track_started=True)
         def run_pipeline(self, project_id: str, request: str) -> dict:
             try:
                 manager = get_workflow_manager()
                 result = manager.run(project_id, request)
                 return result.model_dump()
             except Exception as exc:
                 logger.error("pipeline task failed: %s", exc, exc_info=True)
                 raise

         Why: Tasks are serializable, cancellable, and isolated. One task per project_id
              enforced by Celery's task deduplication. No daemon threads.
```

```
NEW      backend/app/api/middleware/auth.py
         FastAPI middleware: APIKeyMiddleware

         Reads X-API-Key from request headers.
         Validates against VALID_API_KEYS env var (comma-separated list).
         Exempts: GET /health, GET /docs, GET /openapi.json
         Returns 401 on missing key, 403 on invalid key.

         Why: Minimum viable auth. Prevents unauthorized credit consumption.
              Does not require a database — keys are in .env.
```

```
NEW      backend/Dockerfile
         FROM python:3.12-slim
         WORKDIR /app
         COPY requirements.txt .
         RUN pip install --no-cache-dir -r requirements.txt
         COPY . .
         EXPOSE 8000
         CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

NEW      backend/docker-compose.yml
         services:
           api:
             build: .
             ports: ["8000:8000"]
             env_file: .env
             depends_on: [redis]
             volumes: ["./temp-workspace:/app/temp-workspace"]

           worker:
             build: .
             command: celery -A app.tasks worker --loglevel=info
             env_file: .env
             depends_on: [redis]
             volumes: ["./temp-workspace:/app/temp-workspace"]

           redis:
             image: redis:7-alpine
             ports: ["6379:6379"]

         Why: Currently the only way to run the system is uvicorn by hand.
              Docker Compose gives a reproducible one-command startup.
```

```
NEW      backend/app/observability/logging.py
         Configure structlog with:
             - JSON output in production (LOG_FORMAT=json in .env)
             - Plain text in development (LOG_FORMAT=text)
             - Bound context: every log line includes project_id, stage, attempt
             - Request ID injected by middleware into bound context

         Usage pattern:
             log = structlog.get_logger().bind(project_id=project_id, stage=stage_name)
             log.info("stage started")
             log.error("stage failed", error=str(exc))

         Why: Currently log lines have no correlation. A failing pipeline at stage 12
              produces 50+ lines with no way to filter by project.
```

### What to Migrate

```
MIGRATE  All 8 SQLite databases → unified data/ directory

         Current locations (scattered):
             backend/app/memory/memory.sqlite
             backend/app/memory/knowledge.sqlite
             backend/app/memory/learning.sqlite
             backend/app/memory/lessons.sqlite
             backend/app/memory/costs.db
             backend/app/intelligence/file_index.db
             backend/app/session/sessions.db
             backend/data/memory.sqlite (duplicate?)

         Target: backend/data/{name}.db  (all in one place, ignored by git)

         Also: add backend/data/ to .gitignore if not already there
         Also: add Alembic migration baseline for each database schema

         Why: 8 databases in 6 different directories. No consistent location.
              Paths hardcoded as relative strings — break on directory change.
```

### Verification Checkpoint

After Phase 6:
- `docker compose up` starts the full system cleanly
- `POST /api/v1/projects` without X-API-Key returns 401
- `POST /api/v1/projects` with description > 2000 chars returns 422
- Two simultaneous POST /workflow/{id}/start requests result in one running pipeline, not two
- Log output is structured JSON with project_id on every line

---

## Phase 7 — Template Engine + Model Routing (2–3 weeks)

**Goal:** Make cross-project learning real and route each stage to the optimal model.

### What to Update

```
UPDATE   backend/app/memory/learning_loop.py
         Method: record_success() (or add if missing)

         Called automatically by MemoryOrchestrator.record_approval() after every stage.
         Stores: stage_name, project_type (inferred from description), artifact_summary,
                 model_used, tokens_used, retry_count

         Why: Currently LearningLoop is never written to automatically.
              Patterns accumulate only if explicitly called. They aren't.
```

```
UPDATE   backend/app/memory/lesson_store.py
         Method: record() (or add if missing)

         Called automatically by MemoryOrchestrator.record_rejection() after every rejection.
         Stores: stage_name, rejection_type, feedback_text, what_was_tried, retry_strategy_used

         Why: Same as above — LessonStore has no auto-write path from Reviewer rejections.
```

### What to Build New

```
NEW      backend/app/learning/template_engine.py
         Class: TemplateEngine

         extract_template(project_id: str) → ProjectTemplate
             Called after Retro stage (final stage) completes successfully.
             Reads all approved artifacts for the project.
             Extracts: stack_decisions, sprint_structure, file_patterns, lessons_applied
             Stores template in knowledge_base with embedding of original_request

         find_similar(request: str, top_k: int = 3) → list[ProjectTemplate]
             Semantic search over stored templates.
             Returns templates ordered by similarity score.
             Used by MemoryOrchestrator.get_context() for Layer 3 pattern injection.

         inject_template(context: StageContext, template: ProjectTemplate) → StageContext
             Adds template.architecture_decisions to context.patterns for Architect stage
             Adds template.sprint_structure to context.patterns for SprintPlanner stage
             Token budget aware: drops patterns that would exceed budget

         Why: Every project currently starts from zero. The 5th calculator app should
              benefit from the first four. Templates make this explicit and structured.
```

```
NEW      backend/app/llm/model_router.py
         Class: ModelRouter

         STAGE_PROFILES: dict[str, ModelProfile] = {
             "DomainResearch":    ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                               temperature=0.3, max_tokens=4096),
             "ProductOwner":      ModelProfile(provider="claude", model="claude-sonnet-4-6",
                                               temperature=0.1, max_tokens=16384),
             "Architect":         ModelProfile(provider="claude", model="claude-sonnet-4-6",
                                               temperature=0.1, max_tokens=8192),
             "Designer":          ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                               temperature=0.5, max_tokens=4096),
             "BackendDeveloper":  ModelProfile(provider="bedrock", model="qwen.qwen3-vl-235b-a22b",
                                               temperature=0.05, max_tokens=32768),
             "FrontendDeveloper": ModelProfile(provider="bedrock", model="qwen.qwen3-vl-235b-a22b",
                                               temperature=0.05, max_tokens=32768),
             "BugAnalyst":        ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                               temperature=0.2, max_tokens=4096),
             "Document":          ModelProfile(provider="gemini", model="gemini-2.0-flash",
                                               temperature=0.3, max_tokens=4096),
         }

         get_profile(stage: str) → ModelProfile
             Checks env var STAGE_{STAGE_UPPER}_PROVIDER and STAGE_{STAGE_UPPER}_MODEL first
             Falls back to STAGE_PROFILES[stage]
             Falls back to global LLM_PROVIDER + LLM_MODEL

         Why: All stages currently use one global model. Research tasks don't need
              the same model as code generation. Routing reduces cost 40–60%.
```

```
NEW      backend/app/shared/dto/model_profile.py
         Dataclass: ModelProfile
             provider: str     # "bedrock" | "gemini" | "claude" | "ollama"
             model: str
             temperature: float
             max_tokens: int

         Why: Typed profile is passed to LLMManager instead of reading global config.
```

```
UPDATE   backend/app/llm/manager.py
         Method: complete() (or execute())
         
         Accept optional ModelProfile parameter:
             def complete(self, request: LLMRequest,
                          profile: ModelProfile | None = None) -> LLMResponse:
                 if profile:
                     # override provider and model for this call only
                     provider = self._get_provider(profile.provider)
                     request = request.with_model(profile.model)
                     request = request.with_temperature(profile.temperature)
                 else:
                     provider = self._get_default_provider()
                 return provider.execute(request)

         Why: LLMManager currently always uses the global provider. Per-call
              profile override enables model routing without changing global config.
```

### Verification Checkpoint

After Phase 7:
- After a project completes Retro, `template_engine.find_similar("calculator app")` returns that project as a template
- A new "calculator app" project's Architect stage receives the previous calculator's architecture decisions in context
- DomainResearch calls Gemini, BackendDeveloper calls Bedrock — verify in logs
- `STAGE_PRODUCTOWNER_MODEL=claude-opus-5` in .env overrides only ProductOwner's model

---

## Removal Master List

Everything that should be deleted across all phases, consolidated:

| Phase | File | What | Reason |
|-------|------|------|--------|
| 1 | `workflow/engine.py` | `_WORKFLOW_MESSAGE_KEY` constant + all uses | Replaced by per-stage keys |
| 1 | `workflow/engine.py` | All 6 `_with_*` methods | Replaced by MemoryOrchestrator |
| 2 | `workflow/retry_policy.py` | Entire file | Replaced by IntelligentRetryEngine |
| 6 | `api/workflow.py` | `threading.Thread(daemon=True)` pattern | Replaced by Celery task |
| 6 | All manager files | Hardcoded relative DB path strings | Replaced by Path(__file__) anchoring |
| All | `backend/tests/` | Entire directory | Tests were for old behavior; new behavior needs new tests written alongside each phase |

---

## New Files Master List

All new files to create, by phase:

| Phase | File | Purpose |
|-------|------|---------|
| 1 | `memory/orchestrator.py` | Unified memory access layer |
| 1 | `shared/dto/stage_context.py` | Typed context dataclass |
| 1 | `kernel/health_check.py` | Container validation at startup |
| 2 | `workflow/retry_engine.py` | Intelligent retry with rejection-aware strategy |
| 2 | `shared/dto/retry_plan.py` | Typed retry plan |
| 4 | `api/gates.py` | Collaboration gate endpoints |
| 4 | `shared/dto/gate_result.py` | Typed gate result |
| 5 | `execution/sandbox.py` | Code execution sandbox |
| 5 | `shared/dto/sandbox_result.py` | Typed sandbox results |
| 6 | `tasks/pipeline_task.py` | Celery pipeline task |
| 6 | `api/middleware/auth.py` | API key authentication |
| 6 | `Dockerfile` | Container image |
| 6 | `docker-compose.yml` | Local development stack |
| 6 | `observability/logging.py` | Structured JSON logging |
| 7 | `learning/template_engine.py` | Cross-project template learning |
| 7 | `llm/model_router.py` | Per-stage model routing |
| 7 | `shared/dto/model_profile.py` | Typed model profile |

---

## Update Master List

All existing files that need changes, by phase:

| Phase | File | What Changes |
|-------|------|-------------|
| 0 | `workflow/manager.py` | Bug A: save minimal Clarification artifact in else-branch |
| 0 | `workflow/engine.py` | Bug B: fallback to project.json in `_with_clarification_context` |
| 0 | `backend/.env` | Add LLM_MAX_TOKENS=16384, LLM_TEMPERATURE=0.1 |
| 1 | `memory/manager.py` | Add `store_stage_output` / `load_stage_output` methods |
| 1 | `workflow/engine.py` | Replace enrichment chain with single orchestrator call |
| 1 | `workflow/manager.py` | Add memory writes after every stage approval |
| 1 | `kernel/container.py` | Pass MemoryOrchestrator to WorkflowEngine |
| 2 | `workflow/engine.py` | Retry loop reads IntelligentRetryEngine.plan() |
| 2 | `learning/performance_scorer.py` | Write scores to memory, feed into retry engine |
| 3 | `workflow/pipeline_supervisor.py` | Add intelligence layer write trigger after SprintDeploy |
| 3 | `intelligence/context_orchestrator.py` | Return structured empty instead of None |
| 3 | `kernel/container.py` | Remove silent try/except around intelligence singletons |
| 4 | `shared/enums/project_state.py` | Add 2 new gate states |
| 4 | `workflow/pipeline_supervisor.py` | Add gate pause after Architect, SprintPlanner |
| 4 | `workflow/manager.py` | Add gate state handlers in run() |
| 5 | `agents/factory.py` | Pass sandbox results to BugAnalyst |
| 5 | `workflow/pipeline_supervisor.py` | Run sandbox after SprintDeploy, store results |
| 5 | `execution/safety_policy.py` | Add sandbox execution to safety boundary |
| 5 | `backend/.env` | Add SANDBOX_ENABLED, SANDBOX_TIMEOUT |
| 6 | `main.py` | Add auth, rate limit, size limit, logging middleware |
| 6 | `api/project.py` | Add description/name validation |
| 6 | `requirements.txt` | Add celery, redis, structlog, opentelemetry, prometheus |
| 6 | All manager files | Fix hardcoded DB paths to Path(__file__) anchoring |
| 7 | `memory/learning_loop.py` | Add auto-write from MemoryOrchestrator.record_approval |
| 7 | `memory/lesson_store.py` | Add auto-write from MemoryOrchestrator.record_rejection |
| 7 | `llm/manager.py` | Accept ModelProfile override per call |

---

## Phase 8 — Agile Sprint File Management: Update vs. Create

**Goal:** Teach the pipeline the difference between creating a new file and updating
an existing one across sprints. Currently every write is a full overwrite — Sprint 2
BackendDeveloper rewrites Sprint 1's files from scratch with no knowledge of what was
already implemented.

### The Problem in Detail

**Current behavior:**

`WriteProjectFilesAction._build_file_prompt()` passes only:
- The planned file's path, module, and purpose
- The approved architecture summary
- Siblings written in THIS run (for import consistency)
- The project context string

It does NOT pass:
- Whether the file already exists on disk
- The existing file's current content
- Which specific methods/functions need to be added vs. which already exist

`ProjectFileManager.write_file()` calls `target.write_text(content)` — always a complete
replacement. If Sprint 1 wrote `backend/models/user.py` with a `User` model and Sprint 2
plans to add a `profile_picture` field to `User`, the agent rewrites the entire file from
the file plan description alone. It does not see the Sprint 1 implementation, so it
may change existing method signatures, remove existing imports, or rewrite logic that was
already correct.

`PlannedFile` has no `operation` field. There is no way for FileStructurePlanner to express:
"This file already exists — add these methods to it" vs. "This file is new — create it."

**The consequence:**

Sprint N's agents are blind to Sprint (N-1)'s output. They regenerate files that should
only be partially updated. This causes:
- Import paths change between sprints (Sprint 1 uses `from models.user import User`,
  Sprint 2 agent regenerates and writes `from app.models import User`)
- Existing logic is silently replaced by different logic
- Tests written in Sprint 2 test functions that no longer exist because Sprint 3 rewrote them

---

### What to Update

```
UPDATE   backend/app/shared/schemas/file_plan_schema.py
         Class: PlannedFile

         Add field:
             operation: Literal["create", "update", "patch"] = "create"
             change_description: str = ""   # what specifically to add/change, for updates

         Meaning:
             "create"  — file does not exist yet. Generate from scratch.
             "update"  — file exists. Read current content. Add/modify as described
                         in change_description without removing existing functionality.
             "patch"   — file exists. Add only the specific function/method/class
                         described. Touch nothing else.

         Why: FileStructurePlanner must be able to express intent per file.
              Without this field, BackendDeveloper cannot know what to do with
              an existing file — it always regenerates.
```

```
UPDATE   backend/app/workspace/project_files.py
         Class: ProjectFileManager

         Add method: read_file(project_id: str, area: str, relative_path: str) → str | None
             target = self.area_dir(project_id, area) / relative_path
             if not target.exists(): return None
             return target.read_text(encoding="utf-8")

         Add method: file_exists(project_id: str, area: str, relative_path: str) → bool
             target = self.area_dir(project_id, area) / relative_path
             return target.exists()

         Update: write_file() — add write_mode parameter:
             write_mode: Literal["create", "overwrite", "patch"] = "overwrite"
             If write_mode == "create" and target.exists():
                 logger.warning("file already exists, skipping create: %s", target)
                 return existing WrittenFile with bytes_written=0 (no-op)
             If write_mode == "patch":
                 existing = target.read_text() if target.exists() else ""
                 # content is already the full merged file (agent produced it)
                 # just write — the agent did the merging

         Why: Prevents Sprint 2 from silently overwriting Sprint 1 files when
              the intent was "update." The "create" guard catches file plan errors
              where a file is planned as new but already exists.
```

```
UPDATE   backend/app/actions/write_project_files.py
         Class: WriteProjectFilesAction

         Method: _build_file_prompt() — add existing content injection

         Before building the prompt for planned_file:
             existing_content = None
             write_path = self._relative_write_path(planned_file.path)

             if planned_file.operation in ("update", "patch"):
                 existing_content = self.project_file_manager.read_file(
                     project_id, self.area, write_path
                 )

         Pass existing_content to prompt_builder:
             detail = (
                 f"File: {planned_file.path}\n"
                 f"Operation: {planned_file.operation}\n"
                 f"Change description: {planned_file.change_description or 'implement as described'}\n\n"
                 + (
                     f"EXISTING FILE CONTENT (do not remove existing functionality):\n"
                     f"```\n{existing_content}\n```\n\n"
                     if existing_content else
                     "This is a new file. Implement from scratch.\n\n"
                 )
                 + f"Architecture:\n{summarize_architecture(architecture)}\n\n"
                 + f"Files written this sprint:\n{siblings_text}\n\n"
                 + f"Project context:\n{base_content}"
             )

         Update write_file call:
             self.project_file_manager.write_file(
                 project_id, self.area, write_path, file_content,
                 write_mode=planned_file.operation if planned_file.operation != "create" else "overwrite",
                 attempt=attempt
             )

         Why: The agent sees the current file before deciding what to write.
              For "update" operations it receives the full existing content and the
              specific change_description. It produces the complete merged file.
              For "patch" operations it adds only what's described.
```

```
UPDATE   backend/app/prompt/file_plan_builder.py  (or equivalent FileStructurePlanner prompt)
         System prompt additions for Sprint 2+ planning:

         Add this instruction block when sprint_number > 1:

         """
         SPRINT FILE PLANNING RULES (Sprint {sprint_number}):

         You are planning files for Sprint {sprint_number} of {total_sprints}.
         The following files already exist from previous sprints:
         {existing_files_list}

         For each file in your plan, set the "operation" field:
           "create"  — this file does not exist yet
           "update"  — this file exists and needs additions/modifications
                       set "change_description" to exactly what should be added
           "patch"   — this file exists and needs ONE specific addition only

         NEVER plan to "create" a file that already exists.
         NEVER plan to "update" a file with vague change_description like "update as needed."
         Be specific: "Add password_reset() method to UserService class."

         Files from previous sprints:
         {existing_files_list}
         """

         Why: FileStructurePlanner currently plans every sprint as if starting
              from scratch. It must be told what exists so it can correctly classify
              each file as create/update/patch with a specific change description.
```

```
UPDATE   backend/app/prompt/backend_builder.py
UPDATE   backend/app/prompt/frontend_builder.py (if exists)
         System prompt additions:

         When operation == "update":
             "You are modifying an existing file. The current content is shown above.
             Add the described changes WITHOUT removing or rewriting existing functionality.
             Preserve all existing imports, function signatures, and logic unless the
             change_description explicitly says to modify them.
             Output the COMPLETE file with your changes merged in."

         When operation == "patch":
             "You are adding ONE specific element to an existing file.
             Add ONLY what is described in the change_description.
             Do not rewrite existing code. Output the complete file with your addition."

         When operation == "create":
             "This is a new file. Implement it completely from scratch
             according to the architecture and purpose described."

         Why: Without operation-specific instructions, the model treats every
              prompt as "write this file from scratch" regardless of what operation
              was intended.
```

### What to Build New

```
NEW      backend/app/workspace/file_registry.py
         Class: FileRegistry

         Purpose: Single source of truth for what files exist per project per sprint.
                  FileStructurePlanner reads this before planning each sprint.
                  WriteProjectFilesAction updates this after each file is written.

         Methods:
             register(project_id: str, sprint: int, area: str, path: str, operation: str) → None
                 Records that this file was created/updated in this sprint.
                 Stored in memory_manager: key = "files:{project_id}:{area}"
                 Value = list of {path, sprint, operation, written_at}

             get_existing(project_id: str, area: str) → list[str]
                 Returns all file paths that have been registered for this project.
                 Used by FileStructurePlanner to know what already exists.

             get_sprint_files(project_id: str, sprint: int) → list[dict]
                 Returns all files written in a specific sprint.
                 Used by intelligence layer and BugAnalyst.

             was_written_in_sprint(project_id: str, area: str, path: str, sprint: int) → bool
                 Returns True if this file was first created in the given sprint.

         Storage: memory_manager.store/load (inherits from existing MemoryManager)
                  No new database needed — uses existing key/value store.

         Why: Currently there is no record of what files exist across sprints.
              FileStructurePlanner cannot make "create vs. update" decisions
              without knowing what was written before. FileRegistry is this record.
```

```
NEW      backend/app/shared/dto/sprint_file_plan.py
         Dataclass: SprintFilePlan

         Fields:
             sprint_number: int
             new_files: list[PlannedFile]       # operation="create"
             updated_files: list[PlannedFile]   # operation="update" or "patch"
             unchanged_files: list[str]          # paths carried forward with no changes

         Why: Structured separation of create vs. update intent at the sprint level.
              FileStructurePlanner produces this; BackendDeveloper/FrontendDeveloper
              consume it. Makes the intent explicit before any LLM call is made.
```

### How FileStructurePlanner Uses FileRegistry (Sprint 2+ Flow)

```
Sprint 1:
    FileStructurePlanner plans:
        user.py        → operation="create"
        database.py    → operation="create"
        __init__.py    → operation="create"
    BackendDeveloper writes all three files.
    FileRegistry.register() called for each.

Sprint 2 planning:
    FileStructurePlanner receives in context:
        existing_files = FileRegistry.get_existing(project_id, area="backend")
        → ["models/user.py", "config/database.py", "config/__init__.py"]

    FileStructurePlanner plans:
        auth_service.py        → operation="create"  (new)
        models/user.py         → operation="update"  (add password_hash field)
                                  change_description="Add password_hash: str field and
                                  set_password(raw: str) method to User model"
        services/__init__.py   → operation="create"  (new directory)

Sprint 2 execution:
    BackendDeveloper processes auth_service.py:
        → file_exists() = False → generates from scratch
    BackendDeveloper processes models/user.py:
        → file_exists() = True
        → read_file() returns Sprint 1 content
        → prompt includes existing content + change_description
        → model adds password_hash field without removing existing logic
        → write_file() overwrites with merged content
```

### The Prompt Shape for an Update Operation

The prompt sent to the LLM for an "update" file looks like this:

```
File: backend/models/user.py
Operation: update
Change: Add password_hash: str field and set_password(raw: str) method to User model

EXISTING FILE CONTENT (preserve all existing functionality):
```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Files written this sprint (for import consistency):
- backend/services/auth_service.py: JWT authentication service

Architecture: FastAPI + SQLAlchemy + PostgreSQL

Output the COMPLETE file with your changes merged in.
Do not remove or rewrite existing logic.
```

The model sees what exists and what to add. It produces the full merged file.
This is fundamentally different from Sprint 1's prompt which just says "implement User model."

### Verification Checkpoint

After Phase 8:
- Sprint 2 file plan for an existing file shows `operation="update"` not `operation="create"`
- After Sprint 2, `models/user.py` contains both Sprint 1's `User` model AND Sprint 2's new `password_hash` field
- `FileRegistry.get_existing(project_id, "backend")` returns Sprint 1 file paths before Sprint 2 planning
- Running `grep "class User" temp-workspace/{id}/project/backend/models/user.py` finds the class in both Sprint 1 and Sprint 2 artifacts — same class, extended not replaced

---

## Development Rules for This Codebase

These apply to every phase and every PR:

**1. Never modify two architectural layers in the same PR.**
Memory changes and API changes are different PRs. Mixing them makes rollback impossible.

**2. Every removal requires a replacement to be in the same PR.**
Removing `_with_clarification_context` and adding `MemoryOrchestrator.get_context()` go
together. Removing without replacing breaks the pipeline.

**3. New components accept all dependencies via constructor injection.**
No `from ..memory.manager import MemoryManager` inside a method body.
No default `MemoryManager()` construction inside another class.
All dependencies are injected at construction time and registered in `container.py`.

**4. Every new public method has a defined error contract.**
Either it raises a typed exception (defined in `shared/exceptions/`) or it returns a
result type that includes an error field. No silent `except: pass`.

**5. The Reviewer is the quality gate. Don't bypass it.**
If the Reviewer rejects a stage, the fix is in the prompt or the context — not in
changing the Reviewer's rules. The three-tier gate (AUTO_FIX / ASK_HUMAN / FLAG) is
the most valuable component in the system.

**6. Add one log line at the entry and exit of every public method.**
`logger.info("method_name started: key_param=%s", value)` and
`logger.info("method_name completed: result=%s", result)`.
Structured logging (Phase 6) makes these searchable; without them, failures are opaque.

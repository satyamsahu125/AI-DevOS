# AI DevOS — Full System Analysis Report
Generated: 2026-07-28  
Analyst: Senior Software Architect / Development Engineer

---

## 1. SYSTEM FLOW OVERVIEW

```
HTTP POST /workflow/start
        │
        ▼
WorkflowManager.run(project_id, description)
        │  reads Project from WorkspaceManager
        │  emits WebSocket: status_update
        ▼
PipelineSupervisor.run(project_id, engine)
        │
        ├─── Phase 1: DISCOVERY (runs once)
        │    DISCOVERY_STAGES = [strategic_review, product_owner,
        │                        architect, designer, security,
        │                        sprint_planner, scrum_master]
        │    For each stage:
        │      └─► engine.run_stage(stage_name) ─────────────────────────────┐
        │                                                                       │
        ├─── Phase 2: SPRINTS (N iterations)                                   │
        │    SprintSupervisor.run_sprint(sprint_n)                             │
        │    SPRINT_STAGES = [file_planner, backend, frontend,                │
        │                     tech_lead, bug_analyst, qa, sprint_review]       │
        │                                                                       │
        └─── Phase 3: RELEASE (runs once)                                      │
             RELEASE_STAGES = [qa, devops, document, retro]                   │
                                                                               │
◄──────────────────────────────────────────────────────────────────────────────┘
WorkflowEngine.run(stage_name, project_id, content)
        │
        ├── SessionManager.create_session(stage)       → StageSession (in-memory)
        ├── _with_predecessor_message()                → reads prev artifact from disk
        ├── _with_design_context()                     → reads design artifact
        ├── _with_lessons()                            → reads LessonStore (SQLite)
        ├── _with_intelligence_context()               → reads MemoryManager (SQLite)
        │
        ▼
ExecutionManager.execute_stage(project_id, stage, content, attempt)
        │
        ▼
ExecutionEngine.execute(project_id, stage, content, attempt)
        │
        ▼
ExecutionPipeline.run(project_id, stage, content, attempt)
        │
        ├── AgentFactory.create(stage_name)
        │      AgentResolver.resolve(stage) → registry key
        │      AgentRegistry.resolve(key)  → Agent class
        │      returns Agent()
        │
        ├── agent.execute(SimpleNamespace(content=..., project_id=...))
        │      └─► action.run(context, llm_manager)
        │              ├── PromptBuilder.build(context) → prompt string
        │              ├── LLMManager.generate_text(prompt, system_prompt,
        │              │        json_mode=True, max_tokens=8192, num_ctx=8192)
        │              │       └─► OllamaProvider/ClaudeProvider/GeminiProvider
        │              │                .execute(LLMRequest) → LLMResponse
        │              └── _parse_structured(response.content)
        │                      ├── extract_json(text)
        │                      │    ├── try raw parse
        │                      │    ├── _repair_common_json_errors()
        │                      │    ├── _complete_truncated_json()   ← KEY FIX
        │                      │    └── Pydantic model_validate()
        │                      └── raises SchemaValidationError if {} returned
        │
        ├── SafetyPolicy.check(FILE_OVERWRITE, target_path) → ALLOW/WARN/BLOCK
        │
        └── ArtifactManager.save_artifact() → writes JSON to disk
                                           → temp-workspace/{pid}/artifacts/{stage}.json
                                           → temp-workspace/{pid}/artifacts/{stage}.attempt-N.json

        │
        ▼
WorkflowEngine reviews result:
        ├── Reviewer.review(artifact)
        │    ├── Checks content length (< 30 chars → ASK_HUMAN)
        │    ├── Design stage: checks colors/fonts/spacing/breakpoints
        │    ├── Code stages: checks file coverage
        │    └── returns ReviewResult(approved=True/False, findings=[...])
        │
        ├── if approved → SessionManager.close_session()
        │               → LearningLoop.record_trajectory()
        │               → emit WebSocket: stage_complete
        │               → return WorkflowResult
        │
        └── if rejected → SessionManager.increment_retry()
                        → RetryPolicy.should_retry(attempt, limit=3)
                        → if yes: loop with feedback injected into content
                        → if no: raise StageExhaustedException
                               → emit WebSocket: stage_failed
```

---

## 2. MEMORY ARCHITECTURE

```
What gets stored where:

DISK (persists across restarts):
  temp-workspace/{project_id}/
    artifacts/
      {StageName}.json              ← latest approved artifact
      {StageName}.attempt-N.json   ← historical attempts
    project.json                   ← project metadata
    generated/                     ← actual code files written by BackendDev/FrontendDev

SQLite (backend/app/memory/memory.db):
  MemoryManager (key-value) ────── ContextManager, ProjectInitializer
    memory_type=CONTEXT: latest design, workflow message, lessons
    memory_type=PROJECT: per-project facts
    
  LessonStore (SQLite) ─────────── WorkflowEngine after each stage
    stores: schema errors, fix guidance, what worked/failed

  CostTracker (in-memory dict) ─── per-project token/latency totals
    NOT persisted — resets on server restart

IN-MEMORY ONLY (lost on restart):
  SessionManager._sessions        ← all StageSession objects
  ExecutionStateRegistry          ← workflow execution state
  WorkflowStateMachine            ← state transitions
```

---

## 3. STUBS / INCOMPLETE IMPLEMENTATIONS

### CRITICAL STUBS (will silently fail or do nothing)

| Location | Issue | Impact |
|----------|-------|--------|
| `app/llm/provider.py` | `generate()` raises NotImplementedError | Dead abstract — only used if someone calls old `LLMProvider` interface directly |
| `app/shared/interfaces/*.py` | All 15 interface methods raise NotImplementedError | Pure abstract contracts, OK unless inherited without override |
| `app/storage/storage_adapter.py` | `insert/update/delete/select/_execute/_map_result` all raise NotImplementedError | Base class only — SQLiteStorageAdapter overrides all. OK. |
| `app/memory/memory_manager.py:MemoryOrchestrator` | `store()` shadows `self.store` (field name collision!) | **BUG**: `self.store(record)` would call the method, but `self.store.put()` calls the field. Name collision causes AttributeError at runtime. |
| `app/agents/base_agent.py:_build_default_action()` | Abstract but shows [STUB-DOC+PASS] — no body | All concrete agents override this — OK. |

### PARTIAL STUBS

| Location | Issue |
|----------|-------|
| `app/agents/domain_researcher.py` | Likely no real implementation (not in factory registry) |
| `app/agents/descriptor.py` | Not registered in AgentFactory — unreachable from pipeline |
| `app/agents/sprint_deploy.py` | Registered but SprintDeploy not in any stage enum |
| `app/agents/validation.py` | `AgentValidation.validate_name()` — unclear if it does real validation |
| `app/workflow/impact_analyzer.py` | Not called from engine or supervisor — dead code |
| `app/workflow/dependency_graph.py` | Not used in production pipeline — dead code |
| `app/context/context_builder_runtime.py` | ContextBuilderRuntime exists but not wired into any agent |
| `app/workspace/dependency_detector.py` | TODO comment on line 212: pins version as TODO |

---

## 4. IDENTIFIED ERRORS & FAILURE POINTS

### ACTIVE FAILURES (confirmed from logs)

#### F1 — Architect JSON Truncation (PRIMARY ACTIVE FAILURE)
**Status:** Partially fixed, still occurring  
**Root cause chain:**
1. `qwen2.5-coder:7b` default num_ctx in Ollama = 2048 tokens
2. Architect prompt was ~4,300 tokens (full ProductOwner artifact) → only ~0 tokens left for output
3. Even with `num_ctx=8192`, the model generates a few hundred chars then truncates
4. Truncation leaves `"purpose":` with no value → invalid JSON even after repair
5. `extract_json()` returns `{}` → `write_architecture.py` raises SchemaValidationError
6. After 3 retries: stage fails permanently

**Fixes applied in this session:**
- `ArchitectPromptBuilder` now extracts slim context (347 tokens vs 1,967 tokens before)
- `_complete_truncated_json` now handles key-with-no-value and trailing-comma cases
- `num_ctx=8192` added to Ollama options
- `format="json"` grammar-constrained decoding added
- `output_json=True` on LLMAction sends json_mode to all structured stages

**Remaining risk:** Model still cannot reliably produce 5,000+ token JSON output. Even with grammar constraints, `qwen2.5-coder:7b` may not have enough capacity for complex projects.

**Real fix:** Switch to Claude or Gemini provider (now available).

#### F2 — MemoryOrchestrator.store() Name Collision BUG
**Status:** UNCONFIRMED but likely latent  
**Location:** `app/memory/memory_manager.py:41`  
**Code:**
```python
def store(self, record: MemoryRecord) -> MemoryRecord:   # method named 'store'
    saved = self.repository.save(record)
    self.store.put(...)   # 'self.store' is the MemoryStore field — also named 'store'
```
`self.store` resolves to the `MemoryStore` object (assigned in `__init__`), not the method. So `self.store.put(...)` calls `MemoryStore.put()` which may be correct. BUT calling `self.store(record)` from outside would call the METHOD. This is confusing and brittle — a refactor risk.

**Fix needed:** Rename the `MemoryStore` field from `self.store` to `self.memory_store`.

#### F3 — CostTracker Not Persisted
**Status:** Known limitation  
**Location:** `app/llm/cost_tracker.py`  
**Impact:** Token/latency metrics reset on every server restart. The `/metrics` API always shows 0 after restart even for completed projects.

#### F4 — WorkflowEngine StageSession Lost on Restart  
**Status:** ~~Known limitation~~ **CORRECTED — mitigated by CheckpointManager**  
**Correction (2026-07-28):** The original finding was wrong. `CheckpointManager` (SQLite-backed,
`session/checkpoint.py`) saves a `SessionCheckpoint` before every LLM call and deletes it on
clean close. Each checkpoint stores `attempt_number`, `failed_approaches`, and
`last_artifact_summary` — the same data `SessionManager` holds in-process. On restart,
`WorkflowEngine.__init__` calls `_report_incomplete_sessions()` which lists surviving
checkpoints (i.e. sessions that never closed). `SessionManager` is intentionally in-process
only; it is the session lifecycle tracker, not the durability layer — `CheckpointManager` is.

#### F5 — Reviewer Approves Trivially Short Content
**Location:** `app/review/reviewer.py`  
**Issue:** The reviewer flags content < 30 chars as ASK_HUMAN, but for many stages (StrategicReview, Retro) the LLM often produces 200-char responses that look "valid" but are just boilerplate. No semantic quality check beyond length and JSON structure.

#### F6 — SafetyPolicy Blocks Repeat Writes at Attempt > 1
**Location:** `app/execution/pipeline.py` + `app/execution/safety_policy.py`  
**Risk:** `SafetyPolicy.check(FILE_OVERWRITE, path, attempt=N)` — if policy is configured to BLOCK overwrite of existing artifacts, retries on the same stage would be blocked. Need to verify the policy allows overwrite for attempt > 1.

#### F7 — WebSocket Double-Connection (Partially Fixed)
**Status:** Fixed in `useWebSocket.ts` but React Strict Mode in dev still causes brief double events during HMR reloads.

#### F8 — Design Review Modal Never Dismissed Automatically
**Location:** `WorkspacePage.tsx` + workflow state  
**Issue:** `designOpen` is set to true when `pipeline.state` includes `"design_review"`, but if the user closes the modal without approving, `requires_user_action` stays true and the modal re-opens on the next WS event. The user cannot dismiss it without completing the review.

---

## 5. AGENTS REGISTERED BUT UNREACHABLE FROM PIPELINE

| Agent | Registered in Factory | In DISCOVERY_STAGES / SPRINT_STAGES / RELEASE_STAGES |
|-------|----------------------|-------------------------------------------------------|
| `clarification` | YES | NO — called via separate `/qa` endpoint path |
| `sprint_deploy` | YES | NO — called directly by SprintSupervisor (step 6), not via engine.run_stage(). Intentional: needs workspace_manager + deploy_sprint() interface. |
| `production_deploy` | YES | NO — alias for DevOpsAgent, reserved for future RELEASE phase. |
| `domain_researcher` | NO (not in factory) | NO — injected into WorkflowManager as optional pre-pipeline step, intentionally bypasses factory. |
| `descriptor` | NO (not in factory) | NO — not an agent; AgentDescriptor is a dataclass. |

**Correction (2026-07-28):** The original finding ("Dead agents") was partially wrong.
`sprint_deploy` and `domain_researcher` are both actively used — they bypass the factory by design,
not because they are dead code. Only `production_deploy` is a genuine future placeholder.
See EXECUTION_2026-07-28-2.md Task 24 for the full investigation.

---

## 6. PROMPT BUILDER COVERAGE

| Stage | Builder | Slim Context? | json_mode? | Risk |
|-------|---------|---------------|------------|------|
| StrategicReview | StrategicReviewPromptBuilder | Uses full context | YES | Medium — context may be large |
| ProductOwner | ProductOwnerPromptBuilder | Uses full context | YES | Low — inputs are small |
| Architect | **ArchitectPromptBuilder** | **YES (fixed)** | YES | Low now |
| Designer | DesignerPromptBuilder | Uses full arch artifact | YES | HIGH — arch JSON is large |
| Security | SecurityPromptBuilder | Uses requirements | YES | Medium |
| FilePlanner | FilePlanPromptBuilder | Uses arch+design | YES | HIGH — two large artifacts |
| BackendDev | BackendCodePromptBuilder | Uses arch+design+file plan | YES | CRITICAL — 3 large artifacts |
| FrontendDev | FrontendCodePromptBuilder | Uses arch+design+file plan | YES | CRITICAL — 3 large artifacts |
| QA | QAPromptBuilder | Uses code artifacts | YES | HIGH |
| DevOps | DevOpsPromptBuilder | Uses code+QA artifacts | YES | HIGH |
| Document | DocumentationPromptBuilder | Uses all artifacts | YES | CRITICAL — accumulates everything |
| Retro | RetroPromptBuilder | Uses workflow result | YES | Low |

**RECOMMENDATION:** Apply the same slim-context pattern from ArchitectPromptBuilder to Designer, FilePlanner, BackendDev, FrontendDev, and Document stages. Each should extract only the fields its LLM needs, not the full accumulated artifact chain.

---

## 7. LLM PROVIDER COMPARISON

| Provider | Context Window | JSON Mode | Speed | Cost | Recommended For |
|----------|---------------|-----------|-------|------|-----------------|
| Ollama (qwen2.5-coder:7b) | 2048 default (now 8192) | grammar-constrained | Slow (~2-10 min/stage) | Free | Small projects only |
| **Claude (claude-haiku-4-5)** | 200K tokens | Prefill `{` | Fast (~5-15s/stage) | Low (~$0.003/1K tokens) | **RECOMMENDED** |
| **Gemini (gemini-2.0-flash)** | 1M tokens | responseMimeType=json | Fast (~3-10s/stage) | Free tier available | **RECOMMENDED** |
| Bedrock | Varies by model | Varies | Medium | Medium | Enterprise |

**To switch to Claude:**
```bash
# In backend/.env:
LLM_PROVIDER=claude
LLM_MODEL=claude-haiku-4-5
CLAUDE_API_KEY=sk-ant-...
```

**To switch to Gemini:**
```bash
# In backend/.env:
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=AIza...
```

---

## 8. ITEMS NOT WORKING / NEEDS FIX

### P0 — Critical (blocks pipeline completion)
1. **Architect JSON truncation** — Switch to Claude/Gemini. qwen2.5-coder:7b cannot produce 5,000+ token JSON.
2. **Designer/BackendDev/FrontendDev prompts** — Same truncation risk; need slim-context builders.
3. **MemoryOrchestrator field name collision** — `self.store` ambiguity.

### P1 — High (causes data loss or incorrect behavior)
4. **CostTracker not persisted** — Metrics lost on restart.
5. ~~**SessionManager in-memory only**~~ — **CORRECTED**: CheckpointManager provides SQLite durability (see F4 correction above).
6. **Reviewer semantic quality** — Too easy to pass with boilerplate.

### P2 — Medium (UX / reliability)
7. **Design review modal** — Cannot be dismissed without completing review.
8. **Pipeline stage sync** — Sidebar `active` state still briefly de-syncs when WS reconnects.
9. **SafetyPolicy overwrite behavior** — Needs verification for retry attempts.
10. **PromptBuilders for later stages** — All use raw full-artifact context.

### P3 — Low (cleanup)
11. ~~**Dead agents**~~ — **CORRECTED**: sprint_deploy (SprintSupervisor step 6) and domain_researcher (WorkflowManager pre-pipeline) are active. production_deploy is a future RELEASE placeholder. descriptor is a dataclass, not an agent. (See section 5 and EXECUTION_2026-07-28-2.md Task 24.)
12. **Dead workflow modules** (impact_analyzer, dependency_graph) not called.
13. **3 TODO comments** in code (security_builder.py, dependency_detector.py).

---

## 9. CONFIGURATION QUICKSTART

```yaml
# backend/config/config.yaml  — switch to Claude
llm:
  provider: claude
  model: claude-haiku-4-5
  claude_api_key: "sk-ant-..."
  max_tokens: 8192
  timeout: 120

# OR switch to Gemini
llm:
  provider: gemini
  model: gemini-2.0-flash
  gemini_api_key: "AIza..."
  max_tokens: 8192
  timeout: 120
```

---

## 10. FILE COUNTS

| Category | Count |
|----------|-------|
| Python files | 346 |
| Classes | 427 |
| Functions | 1,063 |
| TODO/FIXME comments | 3 |
| Pure stub functions (pass-only) | 0 |
| Abstract interface stubs (raises NotImplementedError) | 40 |
| Unregistered/unreachable agents | 4 |
| Active confirmed bugs | 8 |


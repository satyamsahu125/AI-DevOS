# Phase R1 — Fix What's Broken

**Timeline:** Week 1  
**Priority:** P0 — Must complete before any other work  
**State before:** 7 critical bugs, 3 disconnected systems, 4 failing tests, server crashed on startup  
**State after:** Server starts cleanly, all tests green, chat works, gate feedback consumed, ModelRouter live

---

## Why R1 Before Anything Else

Every bug that ships gets hardened into downstream assumptions. The longer a broken feature stays broken, the more code grows around it that assumes its current (broken) behavior. Fix everything now while the surface area is manageable.

Additionally: 3 major systems (ModelRouter, TemplateEngine, ContextManager) were implemented in Phase 7 but have zero call sites. They represent significant engineering investment that currently has zero impact on any pipeline run.

---

## Bug Fixes (ordered by severity)

### BUG-1: SyntaxError crashes server on startup [DONE]
**File:** `backend/app/execution/code_sandbox.py:142`

Starred expression `*expr if condition else []` inside a tuple literal is invalid Python syntax. Causes SyntaxError at import time, which cascades through the entire import chain and crashes uvicorn before it can serve any request.

**Fix applied:**
```python
# Before (SyntaxError):
for candidate in (
    project_dir,
    *project_dir.iterdir() if project_dir.is_dir() else [],
):

# After (fixed):
subdirs = list(project_dir.iterdir()) if project_dir.is_dir() else []
for candidate in [project_dir, *subdirs]:
```

**Status: FIXED in this session.**

---

### BUG-2: ChatRouter returns LLMResponse object instead of string
**File:** `backend/app/agents/chat_router.py`  
**Methods:** `_read_and_explain_artifact()`, `_general_answer()`

`self.llm.generate_text(...)` returns an `LLMResponse` dataclass. The result is passed directly to `ChatResponse(reply=result, ...)` which expects `str`. The chat endpoint either raises a Pydantic validation error or serializes the entire LLMResponse object as the reply string.

**Fix:**
```python
# Both methods — change:
reply = self.llm.generate_text(...)
# To:
reply = self.llm.generate_text(...).content
```

**Test:** `POST /projects/{id}/chat` with any message must return `{"reply": "...", ...}` where reply is a plain string.

---

### BUG-3: BugAnalyst rollback logic is dead code
**File:** `backend/app/workflow/pipeline_supervisor.py` — `_run_release()` post-bug_analyst

The code checks `result.artifact` but `WorkflowResult` has no `.artifact` field. The `spec_bug` / `architecture_bug` full-pipeline rollback and the `code_bug` targeted-fix path never trigger. BugAnalyst can classify any bug correctly but the fix is never applied.

**Fix:**
1. Add `artifact: dict | None = None` field to `WorkflowResult` (in `shared/dto/workflow_result.py` or wherever defined)
2. In `WorkflowEngine.run()`, populate `result.artifact` with the last parsed artifact dict
3. In `pipeline_supervisor._run_release()`, the existing rollback logic works once `result.artifact` is populated

---

### BUG-4: Human gate feedback stored but never read back
**File:** `backend/app/api/gates.py` writes `gate:feedback:{gate}` → never read

When a human submits revision feedback at an Architecture, Design, or Sprint Plan gate, `_store_gate_feedback()` writes it to MemoryManager. But WorkflowEngine's `_build_retry_content()` (or equivalent enrichment) never reads this key. Human revision guidance is permanently discarded — the next stage runs with no knowledge of what the human asked for.

**Fix:**
```python
# In WorkflowEngine — add _with_gate_feedback() call before the stage that follows each gate
def _with_gate_feedback(self, stage: str, context: dict) -> dict:
    """Inject human gate feedback into the context for the stage after a gate."""
    gate_map = {
        "architecture": "gate:feedback:architecture_review",
        "design": "gate:feedback:design_review",
        "sprint_plan": "gate:feedback:sprint_plan_review",
    }
    for gate_name, key in gate_map.items():
        feedback = self._memory_manager.load(key)
        if feedback:
            context[f"{gate_name}_human_feedback"] = feedback
    return context
```

---

### BUG-5: ModelRouter, TemplateEngine, ContextManager are dead code
**File:** `backend/app/kernel/container.py` + WorkflowEngine

All three are registered in the DI container but never called:

**ModelRouter fix:** In `WorkflowEngine._run_stage()` (or equivalent), before calling `llm.generate_text()`:
```python
profile = self._model_router.get_profile(stage_name)
result = self._llm.generate_text(..., profile=profile)
```

**TemplateEngine fix:**
- After each stage approval: call `template_engine.extract_template(stage_name, approved_artifact)`
- Before building each stage prompt: call `similar = template_engine.find_similar(stage_name, context); if similar: inject_template(...)`

**ContextManager fix:** Remove `context_manager=None` from `container.py`. Fix the attribute name collision (rename to avoid conflict) and re-enable semantic context layer. Layer 3 memory is currently always empty.

---

### BUG-6: WebSocket events are unauthenticated
**File:** `backend/app/api/websocket.py`

`APIKeyMiddleware` enforces `X-API-Key` for HTTP routes, but WebSocket upgrade requests bypass it. Any client who knows a `project_id` can subscribe to all pipeline events, log lines, gate notifications, and artifact content without authentication.

**Fix:**
```python
@router.websocket("/ws/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(default=""),  # X-API-Key passed as query param
):
    if not _validate_api_key(token):
        await websocket.close(code=4001)
        return
    # ... existing logic
```

---

### BUG-7: Production credentials in repository
**File:** `backend/.env`

The `.env` file contains a live `BEDROCK_API_KEY`. If this repository is ever pushed to a remote, the key is compromised.

**Actions:**
1. Rotate `BEDROCK_API_KEY` in AWS console immediately
2. Add `backend/.env` to `.gitignore`
3. Create `backend/.env.example` with all var names, all values as `YOUR_VALUE_HERE`
4. Verify `git status` shows `.env` as untracked (not staged or committed)

---

## Activations (built but disconnected)

### Persist FileRegistry to SQLite
**File:** `backend/app/workspace/file_registry.py`

FileRegistry currently tracks written files in memory only. On server restart, Sprint 2+ receives no existing-file context, so all files are treated as new creates instead of updates. The LLM generates duplicate/conflicting code.

**Fix:** Add SQLite backend using the same pattern as LessonStore/LearningLoop. Table: `file_registry(project_id TEXT, sprint INT, path TEXT, operation TEXT, created_at TEXT)`.

---

## Test Suite

Four tests are known to fail. Fix all four as part of R1:
1. `tests/` tests that import `sentence_transformers` — add `sentence-transformers` to `requirements.txt` or mark tests as `pytest.mark.skipif(no_transformers)`
2. Two stale `Fix009` tests — update to match current behavior
3. Stale stage-order test — update expected order to match current `STAGE_SEQUENCE`

**Exit criteria for R1:** `pytest --tb=short` shows zero failures across all tests.

---

## Exit Criteria

All of the following must be true before R1 is considered complete:

- [ ] Server starts with `uvicorn app.main:app` without error
- [ ] `pytest --tb=short` — zero failures
- [ ] `POST /projects/{id}/chat {"message": "hello"}` returns `{"reply": "<str>", ...}` — reply is a plain string
- [ ] Gate feedback appears in the stage prompt that immediately follows a gate revision (verify via log)
- [ ] ModelRouter profile is logged per stage call (add `logger.debug("[WorkflowEngine] stage=%s profile=%s", stage, profile)`)
- [ ] `.env` is in `.gitignore`, `BEDROCK_API_KEY` is rotated
- [ ] `FileRegistry` table exists in SQLite after first sprint
- [ ] WebSocket connection is rejected with code 4001 when `token` query param is missing/invalid

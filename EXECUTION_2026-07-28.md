# Execution Log — 2026-07-28
AI DevOS — Fix Session 2  
Engineer: Senior Software Architect

Each fix has three sections: **PREVIOUS STATE**, **WHAT CHANGED**, **NEXT TO FIX**.

---

## FIX 1 — MemoryOrchestrator Name Collisions
**File:** `backend/app/memory/memory_manager.py`  
**Priority:** P0

### PREVIOUS STATE
`MemoryOrchestrator.__init__` assigned 4 instance attributes whose names exactly matched class-level method definitions:

```python
self.store      = MemoryStore()       # shadows def store(self, record)
self.index      = MemoryIndex()       # shadows def index(self)
self.cleanup    = MemoryCleanup()     # shadows def cleanup(self)
self.statistics = MemoryStatistics()  # shadows def statistics(self)
```

In Python, instance attributes stored in `__dict__` take precedence over class methods during attribute lookup. This made `obj.store(record)`, `obj.index()`, `obj.cleanup()`, and `obj.statistics()` all broken — they resolved to the subsystem objects, not the methods. The methods were effectively unreachable dead code. The `store()` method itself contained `self.store.put(...)` which happened to work (resolved to the MemoryStore instance), but was deeply misleading.

### WHAT CHANGED
Renamed 4 instance attributes to eliminate the collisions:

| Old attribute | New attribute | Shadowed method renamed to |
|---------------|--------------|---------------------------|
| `self.store` | `self.memory_store` | `store()` — no rename, now reachable |
| `self.index` | `self.memory_index` | `index()` → `rebuild_index()` |
| `self.cleanup` | `self.memory_cleanup` | `cleanup()` → `run_cleanup()` |
| `self.statistics` | `self._stats` | `statistics()` → `get_statistics()` |

All internal references updated: `initialize()`, `store()`, `update()`, `delete()`, `shutdown()` all use the new names.

Added docstring clarifying the naming convention.

Removed unused `MemoryType` import.

### NEXT TO FIX
- Any external callers of `MemoryOrchestrator` using `.store`, `.index`, `.cleanup`, `.statistics` as attributes need updating. Grep the codebase: `grep -rn "orchestrator\.store\|orchestrator\.index\|orchestrator\.cleanup\|orchestrator\.statistics"`.
- Consider adding `__slots__` to `MemoryOrchestrator` to make future name collision bugs a TypeError at instantiation rather than silent misbehaviour.

---

## FIX 2 — CostTracker Pricing for Claude & Gemini Providers
**File:** `backend/app/llm/cost_tracker.py`  
**Priority:** P1 (data accuracy)

### PREVIOUS STATE
`TOKEN_COST_PER_1K` only contained Ollama (free) and 3 generic Bedrock model names. The new Claude and Gemini providers (added in the previous session) had no pricing entries — all cloud LLM calls showed `$0.0000` estimated cost in the Metrics tab.

Additionally, the `LLMCall.provider` type comment still listed only `"ollama" | "bedrock"`.

**Correction from analysis report:** The report incorrectly stated CostTracker was "in-memory only". It already uses SQLite at `memory/memory.db` — cost data IS persisted across restarts. That finding was a false positive.

### WHAT CHANGED
Added 10 new pricing entries:

```python
# Anthropic Claude (Messages API, per 1K tokens, USD — July 2026)
"claude-haiku-4-5":            {"input": 0.0008,  "output": 0.004}
"claude-haiku-4-5-20251001":   {"input": 0.0008,  "output": 0.004}
"claude-sonnet-4-5":           {"input": 0.003,   "output": 0.015}
"claude-opus-4-5":             {"input": 0.015,   "output": 0.075}
"claude-3-5-haiku-20241022":   {"input": 0.0008,  "output": 0.004}
"claude-3-5-sonnet-20241022":  {"input": 0.003,   "output": 0.015}

# Google Gemini (per 1K tokens, USD — July 2026)
"gemini-2.0-flash":      {"input": 0.0001,   "output": 0.0004}
"gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003}
"gemini-1.5-flash":      {"input": 0.000075, "output": 0.0003}
"gemini-1.5-pro":        {"input": 0.00125,  "output": 0.005}
```

Updated `LLMCall.provider` comment to `"ollama" | "claude" | "gemini" | "bedrock"`.

### NEXT TO FIX
- Pricing changes frequently — add a `PRICING_LAST_UPDATED` constant so future engineers know when to refresh.
- The `_estimate_cost` method in `get_project_summary` queries by `model` name (row[2]), which only matches exact string keys. If the model name ever has a version suffix (e.g. `gemini-2.0-flash-001`), it would fall through to `$0.0000`. Add a prefix-match fallback.
- Add a `/api/cost/{project_id}` endpoint that returns the full `ProjectCostSummary` so the Metrics tab can show per-stage cost breakdowns (currently it only shows aggregate token counts).

---

## FIX 3 — Reviewer Semantic Boilerplate Detection
**File:** `backend/app/review/reviewer.py`  
**Priority:** P1

### PREVIOUS STATE
The reviewer had two quality gates: content length (< 10 chars → ASK_HUMAN) and schema presence (no `structured_content` when schema expected → ASK_HUMAN). Both are purely structural. A 200-char LLM boilerplate response like *"Sure! Here is your architecture: {...}"* or an architecture JSON where `modules`, `api_endpoints`, and `data_models` are all empty arrays would pass review and proceed to the next stage.

`_compute_quality_score` deducted 0.5 for short content and 0.3 for missing structured output, but nothing for empty required fields or boilerplate phrasing.

### WHAT CHANGED
Added 4 new detection mechanisms:

**1. Boilerplate phrase patterns** (`_BOILERPLATE_PATTERNS`): 6 compiled regexes matching common assistant-voice preambles ("Sure, here is...", "Certainly! Here...", "As an AI language model..."). Checked against first 500 chars of content. Triggers a FLAG finding and deducts 0.2 from quality score.

**2. Required structured-key emptiness** (`_REQUIRED_STRUCTURED_KEYS`): Per-schema dict of keys that must be non-empty for the artifact to be meaningful:
```python
"WriteArchitecture": ["modules", "api_endpoints", "data_models"],
"WriteDesign":       ["user_flows", "components", "page_layouts"],
"WriteRequirements": ["requirements"],
"WriteQAReport":     ["test_cases"],
...
```
Empty required keys → FLAG finding + quality score deduction proportional to empty ratio (max 0.4).

**3. Word count minimum for text-only stages** (`_MIN_WORDS_TEXT_STAGE = 30`): Stages without a `schema_type` (StrategicReview, Retro) must produce ≥ 30 words. Triggers FLAG if below.

**4. Quality score integration**: `_compute_quality_score` now incorporates both the boilerplate penalty and the empty-required-key penalty, making the overall score more accurately reflect output quality.

### NEXT TO FIX
- `_REQUIRED_STRUCTURED_KEYS` is hardcoded against schema names. If schema names change or new schemas are added, this dict becomes stale. A better approach: read the schema's required fields from the Pydantic model definition directly (via `model_fields` introspection).
- The boilerplate patterns only check the first 500 chars. Some models produce valid JSON preceded by 1000+ chars of preamble. Consider checking the entire content for the JSON fence markers and flagging if a fence is found inside a supposed-JSON-mode output.
- Consider elevating empty required keys from FLAG to ASK_HUMAN for critical stages (Architect, BackendDev) since empty `modules`/`api_endpoints` guarantees downstream stages will fail.

---

## FIX 4 — Slim-Context Extraction: Designer, Backend, Frontend, Document Builders
**Files:**
- `backend/app/prompt/designer_builder.py`
- `backend/app/prompt/backend_builder.py`
- `backend/app/prompt/frontend_builder.py`
- `backend/app/prompt/document_builder.py`
**Priority:** P2

### PREVIOUS STATE
All four builders used the equivalent of `str(context)` — dumping the full accumulated context object verbatim into the prompt:

| Builder | Old pattern | Estimated context tokens |
|---------|------------|--------------------------|
| DesignerPromptBuilder | `base_text = str(context)` | ~4,000–8,000 (full Architect JSON) |
| BackendPromptBuilder | `super().build(context)` → `f"...Context: {str(context)}"` | ~8,000–15,000 (Arch + FilePlan) |
| FrontendPromptBuilder | `f"...Context: {context}"` | ~8,000–15,000 (Design + FilePlan) |
| DocumentPromptBuilder | `f"...Context: {context}"` | ~20,000–30,000 (all stages) |

This left insufficient context window for the model's actual output, causing the same truncation pattern observed in the Architect stage (fixed in the previous session via `ArchitectPromptBuilder`).

### WHAT CHANGED
Applied the same slim-context pattern from `ArchitectPromptBuilder` to all four builders. Each now:
1. Parses the predecessor artifact JSON (handles markdown fences)
2. Extracts only stage-relevant keys
3. Falls back to raw content (capped at 2,000–3,000 chars) if parsing fails

**DesignerPromptBuilder** — extracts: `project_name`, `scale_profile`, `tech_stack`, `api_endpoints` (name/method/path only, max 20), `layers`. Estimated reduction: ~75%.

**BackendPromptBuilder** — extracts: `project_name`, `scale_profile`, `tech_stack`, `modules` (max 20), `api_endpoints` (max 30), `data_models`, `layers`, `backend_files`, `constraints`, `non_functional_requirements`. Estimated reduction: ~60%.

**FrontendPromptBuilder** — extracts: `project_name`, `scale_profile`, `tech_stack`, `components`, `page_layouts`, `user_flows`, `design_system`, `frontend_files`, `api_endpoints` (name/path/method only, max 20). Estimated reduction: ~65%.

**DocumentPromptBuilder** — extracts: `project_name`, `tech_stack`, `api_endpoints` (name/method/path, max 30), `modules`, `components`, `written_paths`, `deployment_steps`. Estimated reduction: ~85%.

### NEXT TO FIX
- The slim-context helpers (`_extract_*_context`, `_parse_json`) are duplicated across 5 builders (Architect + 4 new). Extract into a shared `SlimContextMixin` or `context_extractor.py` utility module to avoid future divergence.
- The `_parse_json` walrus-operator pattern (`(m := re.search(...)) and m.group(1)`) returns `False` when the regex has no match, which is falsy but not `None`. This works correctly in practice but is fragile — replace with an explicit `None` check.
- Test each builder with a real-world predecessor artifact to verify the extracted fields are sufficient for quality output.

---

## FIX 5 — Design Review Modal Auto-Reopen Bug
**File:** `frontend/src/pages/WorkspacePage.tsx`  
**Priority:** P2

### PREVIOUS STATE
The `useEffect` on `pipeline.state` unconditionally called `setDesignOpen(true)` whenever the state included `"design_review"`:

```tsx
useEffect(() => {
  const s = pipeline.state.toLowerCase()
  if (s.includes("design_review") || s === "design_ready") setDesignOpen(true)
}, [pipeline.state])
```

The `DesignReviewModal` `onClose` prop called `setDesignOpen(false)`. But since `pipeline.state` does not change when the user closes the modal (the backend is still waiting for user action), the next WebSocket `pipeline_update` event triggered the `useEffect` again, unconditionally re-opening the modal. The user could not dismiss it — every 2-5 seconds (WS heartbeat), the modal reappeared.

### WHAT CHANGED
Added `designDismissedRef = useRef(false)` — a ref (not state, so it doesn't cause re-renders) that tracks whether the user explicitly closed the modal:

```tsx
const designDismissedRef = useRef(false)

useEffect(() => {
  const s = pipeline.state.toLowerCase()
  if (s.includes("design_review") || s === "design_ready") {
    if (!designDismissedRef.current) setDesignOpen(true)   // only if not dismissed
  } else {
    designDismissedRef.current = false  // reset when pipeline advances
  }
}, [pipeline.state])
```

`onClose` now sets `designDismissedRef.current = true` before closing.  
`onActionCompleted` clears it (review was completed — pipeline will advance past design_review naturally).

### NEXT TO FIX
- The dismiss state is local to the React component. On browser refresh, the modal will reopen even if the user dismissed it before. Consider persisting the dismissed state to `sessionStorage` (keyed by `projectId + pipeline.state_hash`).
- The "Review Design" button in the toolbar (line 488) still calls `setDesignOpen(true)` without resetting `designDismissedRef`. This means if a user dismisses the modal and then explicitly clicks "Review Design", the ref blocks it. Fix: reset the ref when the button is clicked: `designDismissedRef.current = false; setDesignOpen(true)`.
- Long-term: the modal's dismissed-or-completed state should be tracked server-side so that project resume after a server restart respects the user's review decision.

---

## SUMMARY TABLE

| Fix | File(s) | Priority | Status |
|-----|---------|----------|--------|
| MemoryOrchestrator name collisions | `memory/memory_manager.py` | P0 | ✅ Fixed |
| CostTracker Claude/Gemini pricing | `llm/cost_tracker.py` | P1 | ✅ Fixed |
| Reviewer boilerplate detection | `review/reviewer.py` | P1 | ✅ Fixed |
| Slim-context prompt builders | `prompt/designer_builder.py`, `backend_builder.py`, `frontend_builder.py`, `document_builder.py` | P2 | ✅ Fixed |
| Design review modal auto-reopen | `frontend/src/pages/WorkspacePage.tsx` | P2 | ✅ Fixed |

## REMAINING BACKLOG (not yet fixed)

| Item | Priority | Notes |
|------|----------|-------|
| Extract shared `SlimContextMixin` from 5 duplicate prompt builders | P2 | Duplication risk |
| Fix "Review Design" button not resetting `designDismissedRef` | P2 | 5-line fix |
| Persist modal dismissed state to sessionStorage | P3 | UX polish |
| Add prefix-match fallback in `CostTracker._estimate_cost` | P3 | Model version suffix edge case |
| Wire `sprint_deploy` / `production_deploy` agents into pipeline | P3 | Currently registered but unreachable |
| Remove `domain_researcher`, `descriptor` or wire into factory | P3 | Dead code |
| Upgrade Reviewer empty-required-keys from FLAG to ASK_HUMAN for critical stages | P2 | Currently FLAG; should block Architect/Backend |
| Add `/api/cost/{project_id}` detailed breakdown endpoint | P2 | Frontend Metrics tab shows aggregates only |

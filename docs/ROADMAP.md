# Implementation Roadmap

**Status:** Canonical. Supersedes the "Future Roadmap"/"Volume 8" lists scattered across the
prior doc corpus (`DOC-050`, `DOC-051`-`060`, Handbook Ch.26). Phases below are sequenced by
dependency, not by calendar week — "Week N" labels are carried over from the source prompt for
continuity but should be read as "phase N," since actual duration depends on execution
capacity, not a fixed calendar.

Two conflicts were found between this roadmap's originally-requested wording and either the
codebase reality (PROMPT 2) or the research findings (PROMPT 3). Both are flagged and resolved
below rather than silently implemented as originally worded, per this prompt's own rule.

---

## Phase 1 — Fix Current Bugs (Week 1)

These are not new features — they are the P0/P1 items from PROMPT 2's Priority Fix List,
without which nothing in Phases 2-5 has anything real to attach to.

- Fix the retry loop in `WorkflowEngine` (`RetryPolicy` is currently defined but never
  invoked anywhere — confirmed BUG in PROMPT 2).
- Fix `SessionManager` (currently returns a plain dict with no `retry_count` field and is
  never actually called by anything).
- Wire all 6 agents to `LLMManager` (currently every agent echoes its own prompt text or
  `str(context)` as the "generated" artifact — confirmed as the single most critical bug).
- Connect `ContextBuilder` to `MemoryManager` (currently hardcodes placeholder strings
  `"demo"`/`"requirements"`/`"architecture"` instead of reading real memory).
- Fix duplicate implementations (at minimum: the two `ExecutionEngine` classes, two
  `MemoryManager` classes, two `LLMManager` classes, two `OllamaProvider` classes, two
  `ArtifactManager` classes, and the three parallel DI/bootstrap stacks — all confirmed
  orphaned-vs-live pairs in PROMPT 2).
- Add logging everywhere (every public runtime method should log start/finish/failure —
  currently most managers have no logging at all).
- Standardize timestamp handling. **Correction:** PROMPT 2's codebase audit found no actual
  `datetime.utcnow()` deprecation warnings in `backend/app` (a targeted grep found zero
  matches) — the real, related issue is that `datetime.now()` is used inconsistently across
  10 files (`repository_models.py`, `llm_response.py`, `provider_health.py`,
  `workflow.py`, `stage_session.py`, `prompt_package.py`, `stage_artifact.py`, `review.py`,
  `project.py`, `memory_entry.py`) with no consistent timezone-awareness. This item is kept
  but re-scoped to reflect what's actually in the code: standardize on timezone-aware UTC
  timestamps everywhere.

## Phase 2 — Structured Outputs (Week 2, from MetaGPT)

- Add an `Action`-style layer inside `BaseAgent.execute()` (research §A2) — a stateless,
  reusable "build prompt → call `LLMManager` → parse into schema" helper, not a new public
  agent contract.
- Add structured artifact schemas (Pydantic models) per `ARTIFACT-SCHEMAS.md`.

### ⚠️ Conflict flagged and resolved: "Message bus for inter-agent communication"

The originally-requested item read "Add Message bus for inter-agent communication." Research
§A1/§A6 explicitly found that MetaGPT's `Environment.publish_message`/pub-sub bus is a
**direct agent-to-agent communication mechanism** and flagged it as conflicting with AI
DevOS's non-negotiable "no direct agent-to-agent communication — all coordination through the
Workflow Engine" rule. A literal "message bus" would reintroduce exactly that conflict.

**Resolution:** what is actually built is a **`Message` envelope** (research §A1's reusable
idea) attached as metadata on `StageArtifact` — fields `content`, `instruct_content`
(structured payload), `cause_by`/`sent_from` (provenance: which stage/agent produced it) — and
it is **persisted by the Memory Manager and read back by the Context Builder**, exactly like
every other memory-mediated artifact. There is no transport, no subscription, no routing table,
and no path by which one agent invokes or messages another directly. The word "Message" is
kept (it's a useful name for the envelope), but "bus" is dropped from the design entirely.

- Add token cost tracking (feeds `ObservabilityMemory`, per `MEMORY-ARCHITECTURE.md`).

## Phase 3 — Learning System (Week 3, from ruflo)

- `KnowledgeMemory` (HNSW + SQLite, or `chromadb`/`sqlite-vec` — see backend note in
  `MEMORY-ARCHITECTURE.md`).
- `LearningLoop` (trajectory recording, simplified per `LEARNING-SYSTEM.md` Layer 2 — no RL).
- `LessonStore` (human-readable lessons, `LEARNING-SYSTEM.md` Layer 1 — build this first
  within the phase, since it needs no vector infrastructure and delivers value before Layer 2/3
  are ready).
- `ObservabilityMemory` (LLM call metrics — also fixes the confirmed PROMPT 2 bugs where
  `OllamaProvider.health()` never measures real latency and `LLMManager.health()` never
  actually calls the provider).

## Phase 4 — Expanded Stages (Week 4, from gstack)

- Safety guardrails (`SafetyPolicy`, `FreezePolicy` — see `SAFETY-POLICY.md`).
- Context checkpointing for crash recovery (`SessionManager` checkpoint save/restore, per
  research §C4).
- New agents: `SecurityAgent`, `DocumentAgent`, `RetroAgent`, `StrategicReviewAgent` (per
  `AGENT-PROFILES.md`; note `PlannerAgent` already exists and is *not* new — see
  `STAGE-FLOW.md`'s flagged conflict).

### ⚠️ Correction: Reviewer upgrade model

The originally-requested item read "Reviewer upgrade: three-tier (AUTO_FIX / ASK_HUMAN /
FLAG)." Research §C6 found that gstack's actual reviewer model is **not** a single three-tier
system — it is **two independent axes**: Severity (Critical / Informational / Specialist) ×
Action (AUTO-FIX vs ASK, decided by "would a senior engineer apply this without discussion?"),
plus a separate 1-10 confidence gate with suppression bands and fingerprint-based dedup of
previously-skipped findings. This is a factual correction from the research, not a principle
conflict — the two-axis model is what will actually be built, since it is more precise and
directly grounded in the source material. "FLAG" as a literal third tier does not exist in the
source; low-confidence findings are suppressed to an appendix instead, which serves the same
practical purpose.

## Phase 5 — Swarm & Federation (Future, from ruflo)

- Reserve (not implement) an `execution_topology` config field, starting with the single
  legal value `"linear"` and forward-compatible with `"hierarchical"`/`"mesh"` later
  (research §B4) — no coordinator logic is built in this phase.
- Parallel stage execution — explicitly future; the current pipeline is fixed-linear and
  Reviewer-gated at every stage, and research §B5 recommends against porting any dynamic
  agent-spawning/consensus mechanism at all, even in this future phase, since it conflicts
  with the fixed-roster principle. If parallel execution is ever built, it must remain within
  the fixed roster (e.g. BackendDeveloper and FrontendDeveloper running concurrently, since
  neither depends on the other's output) rather than a dynamically-sized agent pool.
- Agent federation — explicitly future and unscoped; no design work has been done on this
  beyond noting it as a named aspiration, consistent with how the source Handbook/research
  treated it.

---

Docs updated. Ready for PROMPT 5.

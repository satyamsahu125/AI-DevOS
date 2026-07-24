# Learning & Self-Improvement System

**Status:** Canonical. Defines the three-layer learning system adopted from research
(PROMPT 3, §B2/§C5). All three layers are owned by the **Memory Manager** — none of them
grants an agent direct storage access; all reads/writes flow through the same Context
Builder / extraction-on-approval pipeline as every other memory type in
`MEMORY-ARCHITECTURE.md`.

**Explicit non-goal:** none of the three layers implements reinforcement learning, gradient
updates, or on-line policy training. Per research §B2/§B5, that entire class of technique
(PPO/DQN/SARSA/A2C, LoRA, EWC continual-learning regularization) was evaluated and rejected —
it requires training infrastructure this project does not have and does not need for a
Reviewer-gated, deterministic pipeline.

---

## Layer 1 — LessonStore (human-readable, per-project lessons)

- **What:** structured lessons distilled from reviewer feedback — a curated knowledge base,
  not a statistical model (gstack `/learn`-derived, research §C5).
- **When recorded:** after every approved *or* rejected stage — a rejection is often the more
  instructive event.
- **When retrieved:** at the start of the same stage in a future run (e.g. `BackendDeveloper`
  reads `BackendDeveloper`-tagged lessons before executing).
- **Format:** `{skill/stage, type: pattern|pitfall|preference|architecture|tool, key, insight,
  confidence (1-10), source: observed|user-stated, files[]}`.
- **Storage:** append-only JSONL, one file per project.
- **Deduplication:** same `key`+`type` pair collapses to the newest entry.
- **Pruning:** human-in-the-loop only (Remove/Keep/Update prompts when an entry references a
  file that no longer exists, or when two entries contradict) — **never automatic deletion**.
  This mirrors gstack's model exactly and is intentionally conservative: an automated
  forgetting mechanism could silently discard a still-valid lesson.

## Layer 2 — LearningLoop (vector semantic search)

- **What:** trajectory vectors capturing `{task input, produced artifact, retry count, final
  reviewer verdict}`, embedded and indexed for similarity search (ruflo ReasoningBank-derived,
  simplified per research §B2).
- **When recorded:** after every stage completion, approved or rejected — unlike LessonStore,
  every trajectory is recorded regardless of whether it produced an explicit lesson.
- **When retrieved:** before every agent run, the Context Builder queries for the top-3 most
  similar past trajectories for that stage and injects them as precedent.
- **How:** HNSW cosine-similarity search (`hnswlib`, or `chromadb`/`sqlite-vec` — see
  `MEMORY-ARCHITECTURE.md`'s `KnowledgeMemory` backend note; `LearningLoop` may share the same
  vector-index infrastructure as `KnowledgeMemory` since both are similarity-search memory
  types, but they are logically distinct: `KnowledgeMemory` indexes *artifacts*, `LearningLoop`
  indexes *trajectories including outcome*).
- **No separate "judge" step is implemented.** Research §B2 notes ReasoningBank's `judge()`
  step is redundant here — AI DevOS's Reviewer *already* produces the pass/fail verdict that
  would otherwise need a separate rule-based judge; `LearningLoop` simply reuses that verdict.
- **No consolidation/dedup/contradiction-detection pass is implemented initially** — this is
  explicitly deferred until trajectory volume actually makes retrieval noisy (flagged as
  future work in PROMPT 3's Priority table, not an initial requirement).

## Layer 3 — AgentPerformance (metrics)

- **What:** aggregate performance stats per stage/agent: `success_rate`, `avg_retries`,
  `avg_latency`.
- **When updated:** after every stage completion (approved or rejected), as a rolling
  aggregate — not a per-call record (the per-call records themselves live in
  `ObservabilityMemory`, see `MEMORY-ARCHITECTURE.md`; `AgentPerformance` is a derived,
  read-only rollup computed from `ObservabilityMemory` + `ReviewMemory`, not a separately
  written memory type).
- **Used by:** WorkflowEngine, for **future** topology/routing decisions (e.g. deciding
  whether a stage needs a different model, or flagging a stage with a persistently low
  success rate for human attention). **Not used today** — AI DevOS's pipeline is currently
  fixed and linear (see `execution_topology` reservation in PROMPT 3 §D1); this layer exists
  so that data collection starts now, even though no decision-making consumes it yet.

---

## Relationship between the three layers

```
Stage completes (approved or rejected)
        │
        ├──▶ ReviewMemory: raw reviewer verdict recorded (unchanged, existing memory type)
        │
        ├──▶ LearningLoop: trajectory (input+output+retries+verdict) embedded and indexed
        │
        ├──▶ ObservabilityMemory: raw per-LLM-call metrics recorded (latency, tokens, errors)
        │
        └──▶ (if a durable, non-obvious insight exists) LessonStore: human-readable lesson recorded
                     │
                     ▼
        AgentPerformance: rolling aggregate computed from ObservabilityMemory + ReviewMemory
                     │
                     ▼
        (future) WorkflowEngine topology/routing decisions
```

Layer 1 (LessonStore) is the cheapest to build and the most immediately useful — it requires
no vector infrastructure. Layers 2 and 3 both depend on the vector-index backend also used by
`KnowledgeMemory`, and are therefore sequenced after it in the roadmap (`ROADMAP.md`, Phase 3).

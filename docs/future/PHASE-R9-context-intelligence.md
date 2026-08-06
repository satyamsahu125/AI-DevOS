# Phase R9 — Context Intelligence + Fast Mode

**Timeline:** Week 12–14  
**Depends on:** R1 (ContextManager re-enabled, ModelRouter wired) — R9 completes and validates what R1 started  
**Problem:** Three major Phase 7 systems (ContextManager, ModelRouter, TemplateEngine) are active (after R1) but need tuning and measurement. Also: the full 19-stage pipeline is overkill for simple prototypes.  
**Outcome:** Context intelligence stack is measured and tuned. Quick Build mode delivers a working prototype in one sprint without the enterprise process stages.

---

## Quick Build Mode

### What is Quick Build?

A stripped pipeline for prototypes: skip Security review, Document, Retro, Strategic brief. Run everything else in a single sprint of up to 5 files per stage.

**Full mode pipeline (current):**
Clarification → StrategicReview → DomainResearch → Architect → HumanGate → Designer → HumanGate → SprintPlanning → HumanGate → BackendDeveloper (N sprints) → FrontendDeveloper (N sprints) → QA → BugAnalyst → Integration → Security → Document → Retro → Deploy

**Quick Build pipeline:**
Clarification → DomainResearch → Architect → Designer → BackendDeveloper (1 sprint, max 5 files) → FrontendDeveloper (1 sprint, max 5 files) → Integration → QA → Deploy

**Skipped:** StrategicReview, all 3 HumanGates, SprintPlanning, Security, Document, Retro

### API Change

```python
# POST /projects
{
  "name": "My App",
  "requirements": "...",
  "mode": "quick"  # or "full" (default)
}
```

### UI Change

Project creation dialog: **"Full Build"** (recommended) vs **"Quick Build"** (prototype in minutes). Show estimated time and feature comparison.

Label all Quick Build projects with a "Prototype" badge in the project list. Show a banner inside the project: "This project was built in Quick Build mode — Security, Documentation, and Strategic Review were skipped."

---

## Context Intelligence Tuning

### ModelRouter — validate and tune profiles

**Current profiles** (from Phase 7 implementation):
- Code stages: temperature=0.05, max_tokens=16384 ✓ — good for deterministic output
- Creative stages: temperature=0.4 — may be too high, monitor
- Review/QA: temperature=0.1 — good

**R9 actions:**
1. Add logging to verify ModelRouter profile is applied for every stage call (should be done in R1, confirm here)
2. After 20+ pipeline runs, query LearningLoop trajectory data: correlation between temperature profile and approval rate
3. Adjust profiles based on evidence, not assumptions

### TemplateEngine — measure injection impact

**R9 actions:**
1. After 10+ pipeline runs, query TemplateEngine: how many templates extracted? How many injections?
2. Compare approval rates for stages where template was injected vs not injected
3. If approval rate improves with injection: increase injection threshold (use templates more aggressively)
4. If no improvement: investigate template quality — are templates too generic to be useful?

### ContextManager — validate Layer 3 semantic retrieval

**R9 actions:**
1. After re-enabling ContextManager in R1, verify that Layer 3 (semantic search) actually returns relevant past decisions
2. Add logging to StageContext assembly: log which layers contributed content for each stage
3. If Layer 3 frequently returns irrelevant content: tighten the HNSW search threshold

---

## Context Window Budget Management

When cumulative tokens for a project run exceed 75% of the provider limit:

1. **Summarize completed stage artifacts** into a compact "project memory" blob:
   ```
   Project: {name}
   Architecture: {3-sentence summary}
   Files generated so far: {list}
   Key decisions: {bullet list}
   Known constraints: {bullet list}
   ```
   
2. **Replace full artifact content** in WorkflowEngine context with the summary

3. **Log warning** and broadcast context_warning event (from R7)

4. **Do not fail** — continue the pipeline with reduced context rather than aborting

---

## Exit Criteria

- [ ] `POST /projects { mode: "quick" }` runs a 1-sprint pipeline without Security/Doc/Retro stages
- [ ] Quick Build completes and produces verified code (R2 sandbox passes)
- [ ] Quick Build project is labeled "Prototype" in UI
- [ ] `GET /analytics/stage/BackendDeveloper` shows temperature profile in metadata (confirming ModelRouter is active)
- [ ] At least one TemplateEngine injection logged after building 5+ projects of similar type
- [ ] Context window budget warning fires when a project exceeds 75% of provider token limit
- [ ] All R1–R8 exit criteria still passing

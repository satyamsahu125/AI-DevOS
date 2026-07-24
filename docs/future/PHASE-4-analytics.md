# Phase 4 — Cost & Learning Analytics

## Problem, today

The system already records a lot: `CostTracker` logs tokens/latency per stage/agent/project,
`LearningLoop` logs every attempt (approved or rejected) as a `Trajectory`, `LessonStore` writes a
human-readable lesson per approval. None of it is surfaced anywhere except a raw `GET
/projects/{id}/cost` JSON blob and a generic key/value dump on `MemoryPage`. There's also a real
structural gap: the `trajectories` table has no `project_id` column (`LearningLoop.count_all_trajectories()`
is explicitly documented as "necessarily global" for this reason) — so per-project learning stats
aren't queryable at all today, only global-across-every-project ones.

## Why this matters

This is a lot of already-collected signal with zero payoff for the user. A user running several
projects has no way to see "which stage fails most often," "how much did this project cost in
tokens," or "what has the system actually learned that's being reused" — despite all of that being
computed and stored today.

## How to build it

1. **Add `project_id` to the trajectories table** (migration: add column, backfill NULL for old
   rows) so `LearningLoop.get_agent_performance()`/failure-pattern queries can be scoped per project,
   not just per stage globally.
2. **A real Analytics view**, replacing/extending the current `MemoryPage`: per-project cost
   (`CostTracker`), per-stage success rate and average retries (`LearningLoop.get_agent_performance()`),
   and the lessons actually recorded (`LessonStore.get_lessons()`) — rendered as something a human
   would actually read, not a raw key/value list.
3. **Surface KnowledgeMemory reuse** — when `get_relevant_patterns()` actually returns a match that
   gets injected into a stage's prompt, log that as a `ProjectEventLog` event ("reused a pattern from
   project X's Architect stage") so the user can see the cross-project learning actually happening,
   not just trust it's there.

## Advantage

Turns "the system has a learning loop" from a backend implementation detail into something the user
can actually see working — which stages are reliable, which are expensive, and what's been learned
and reused — instead of data that's collected and never looked at again.

# Phase 5 — Multi-User & Auth

## Problem, today

There is no authentication or authorization anywhere in the API. Every endpoint under `/projects`,
`/workflow`, `/settings` is open to anyone who can reach port 8000 — including the Bedrock API key
once one is configured (`GET /settings/llm` does mask it, but `POST /settings/llm` accepts a new one
from anyone). This is fine for a single local developer running the tool against their own machine
(today's actual usage), and deliberately out of scope until then — but it's the one gap that blocks
this from ever being run anywhere multi-user (a shared server, a hosted version, a team tool).

## Why this matters

This phase should stay last on purpose: adding auth before the product itself is worth sharing is
wasted effort, and retrofitting it onto a system with more state (Phases 1-4) is strictly easier
once those shapes are stable than doing it first and re-threading it through every later addition.

## How to build it

1. **User accounts + session auth** (even a minimal JWT-or-session-cookie scheme is enough to start
   — this doesn't need to be elaborate).
2. **Project ownership.** Add an `owner_id` to `Project` (`app/shared/models/project.py`) and filter
   every list/get/delete by the requesting user — the isolation pattern already exists for
   `project_id` (`MemoryManager`'s `"{project_id}:{key}"` namespacing, `WorkspaceManager`'s
   per-project directories); this is the same pattern one level up.
3. **Scope secrets per user, not globally.** Right now the Bedrock API key is one global setting in
   `backend/.env`, shared by whoever's running the process. Per-user credential storage (encrypted
   at rest, never logged) would need to replace that single shared value.
4. **Rate limiting / cost caps per user** — reusing `CostTracker`'s existing per-project token
   accounting (Phase 4) as the basis for a per-user spend cap, so one user's runaway build can't
   burn another user's Bedrock budget.

## Advantage

The only thing standing between "a tool I run on my own machine" and "a tool a team could actually
share" is this phase — everything else (isolation, memory, real code generation, cost tracking) is
already built in a way that's namespaced and ready to be scoped one level up to "per user" instead of
just "per project."

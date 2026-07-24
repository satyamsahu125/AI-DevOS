# Future Scope — Phase Index

Each phase below is its own file: problem, why it matters, how to build it, and the concrete
advantage once it exists. Ordered by dependency and payoff, not by difficulty — Phase 1 makes
everything already built actually trustworthy before anything else is worth adding on top.

| Phase | Title | One-line problem |
|---|---|---|
| [1](./PHASE-1-verified-output.md) | Verified Output | Generated code is never actually run before being called done |
| [2](./PHASE-2-human-in-the-loop.md) | Real Human-in-the-Loop | A stage that exhausts retries just fails — "ASK_HUMAN" doesn't actually ask anyone |
| [3](./PHASE-3-deployment-packaging.md) | Deployment & Packaging | DevOps stage only writes advice, never a Dockerfile/CI file a human could use |
| [4](./PHASE-4-analytics.md) | Cost & Learning Analytics | Learning/cost data is recorded but never surfaced anywhere in the UI |
| [5](./PHASE-5-multi-user-auth.md) | Multi-User & Auth | Zero access control — anyone hitting the API sees/controls every project |

Do not start a phase out of order without a specific reason — Phase 2 (real pause/resume) is much
harder to bolt on correctly once Phase 3/4 add more state that a paused build would need to
account for.

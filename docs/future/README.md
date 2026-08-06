# AI DevOS — Future Roadmap

**Updated:** August 2026 — replaces all previous future plans.

This roadmap is grounded in two inputs: (1) a full implementation audit, and (2) competitive analysis of Emergent (emergent.sh) — the leading autonomous coding platform ($100M, 3M users).

Each phase delivers a **fully functional, testable product increment**. No phase introduces partially-completed systems.

---

## Roadmap Phases

| Phase | Name | Outcome | Timeline |
|-------|------|---------|----------|
| [R1](./PHASE-R1-fix-bugs.md) | Fix What's Broken | Zero failing tests, all 7 critical bugs resolved | Week 1 |
| [R2](./PHASE-R2-verifiable-code.md) | Verifiable Code | Generated code passes lint/syntax/build before called complete | Week 2–3 |
| [R3](./PHASE-R3-real-deployment.md) | Real Deployment Output | DevOps stage writes Dockerfile, docker-compose.yml, CI config | Week 3–4 |
| [R4](./PHASE-R4-git-integration.md) | Git Integration | Every project is a portable git repo, export to GitHub | Week 4–5 |
| [R5](./PHASE-R5-live-preview.md) | Live App Preview | Running app served in UI iframe during build | Week 5–7 |
| [R6](./PHASE-R6-integration-agent.md) | Integration Agent | Generated apps wire to Stripe, auth, storage, email | Week 7–9 |
| [R7](./PHASE-R7-analytics.md) | Analytics Dashboard | Cost, quality, and learning data surfaced in UI | Week 9–10 |
| [R8](./PHASE-R8-auth-rbac.md) | Multi-User Auth + RBAC | JWT auth, project ownership, role-based access | Week 10–12 |
| [R9](./PHASE-R9-context-intelligence.md) | Context Intelligence + Fast Mode | ContextManager + ModelRouter + TemplateEngine live; Quick Build mode | Week 12–14 |
| [R10](./PHASE-R10-scale.md) | Scale + Production Hardening | PostgreSQL, Redis, Celery, OpenTelemetry | Week 14–18 |

---

## Strategic Direction

AI DevOS is the **enterprise-grade, self-hosted autonomous software engineering platform for professional teams**.

- Not competing head-on with Emergent's consumer vibe-coding market
- Winning on: process depth, audit trail, human gates, self-hosted economics (local LLM support), change management, security review, and 4-layer persistent memory

See [CTO_STRATEGY_REPORT.html](../CTO_STRATEGY_REPORT.html) for the full 13-section analysis including the complete AI DevOS vs Emergent comparison.

---

## Archived Plans

The following previous future plans are superseded by this roadmap and kept for reference only:

- `PHASE-1-verified-output.md` — sandbox concepts incorporated into R2
- `PHASE-2-human-in-the-loop.md` — human gates fully implemented in Phase 4; remaining gaps in R1/R8
- `PHASE-3-deployment-packaging.md` — superseded by R3 (real deployment output)
- `PHASE-4-analytics.md` — incorporated into R7
- `PHASE-5-multi-user-auth.md` — incorporated into R8

# Documentation Index

**Last Updated**: 2026-08-07
**Master Document**: `CURRENT-STATE.md` (authoritative system description)

---

## Quick Navigation

### 📋 Start Here
- **[CURRENT-STATE.md](CURRENT-STATE.md)** — **AUTHORITATIVE** system description (what's actually implemented)
- **[COMMANDS.md](COMMANDS.md)** — How to set up, run, and test the system
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** — System overview

### 🏗️ Architecture & Design
- **[STAGE-FLOW.md](STAGE-FLOW.md)** — 19-stage pipeline specification
- **[ROADMAP.md](ROADMAP.md)** — Implementation roadmap + what's next

### 🔍 Audit & History
- **[AUDIT_EXECUTIVE_SUMMARY.md](AUDIT_EXECUTIVE_SUMMARY.md)** — 1-page quick reference (2026-07-25)
- **[AUDIT_FINAL_FINDINGS.md](AUDIT_FINAL_FINDINGS.md)** — Critical issues + fixes (2026-07-25)
- **[AUDIT_TECH_DEBT.md](AUDIT_TECH_DEBT.md)** — Tech debt inventory
- **[AUDIT_COMPONENT_INDEX.md](AUDIT_COMPONENT_INDEX.md)** — Component status matrix
- **[AUDIT_ARCHITECTURAL.md](AUDIT_ARCHITECTURAL.md)** — Full architectural audit

---

## Document Status

### ✅ Current (Up-to-Date as of 2026-08-07)

| Document | Purpose | Last Updated |
|----------|---------|--------------|
| CURRENT-STATE.md | System description (AUTHORITATIVE) | 2026-08-07 |
| PROJECT_OVERVIEW.md | System overview | 2026-08-07 |
| STAGE-FLOW.md | 19-stage pipeline | 2026-08-07 |
| ROADMAP.md | Implementation roadmap | 2026-08-07 |
| COMMANDS.md | Setup + run + test | 2026-07-24 |

### ⚠️ Historical (Session logs — do not update)

These are session-by-session implementation logs kept for audit trail:

| Document | Content |
|----------|---------|
| SESSION-LOG-*.md (multiple) | Per-session fix/feature logs |
| AUDIT_*.md (5 files) | 2026-07-25 architecture audit |
| execution-log.md | Old execution tracking |
| repository-certification.md | Old planning |
| foundIssue.md | Bug tracking log |
| new_update.md | Change log |

---

## For Different Audiences

### 👤 New Developer
1. Read: **COMMANDS.md** (setup instructions)
2. Read: **PROJECT_OVERVIEW.md** (system overview)
3. Read: **STAGE-FLOW.md** (19-stage pipeline)
4. Explore: `backend/app/` (code structure)
5. Run tests: `python -m pytest tests/ -q`

### 🏢 Product Manager
1. Read: **PROJECT_OVERVIEW.md** (1 page)
2. Read: **CURRENT-STATE.md** (implementation status)

### 🛠️ Operations / DevOps
1. Read: **COMMANDS.md** (setup, health checks)
2. Read: **CURRENT-STATE.md** § Configuration
3. Check: `backend/.env` for all runtime config

### 🏛️ Architect / CTO
1. Read: **STAGE-FLOW.md** (pipeline design)
2. Read: **CURRENT-STATE.md** (full status)
3. Read: **ROADMAP.md** (what's next)

---

## Key Facts (as of 2026-08-07)

- **19 pipeline stages** across 3 phases (Discovery → Sprint loop → Release)
- **JWT authentication + RBAC** — per-user project isolation enforced
- **Mobile-aware pipeline** — Designer, Frontend, DevOps all dispatch on `project_type`
- **ScrumMaster wired** — runs per-sprint before FileStructurePlanner (fixed 2026-08-07)
- **WebSocket real-time events** — multi-tab, thread-safe
- **6 memory stores** — SQLite + HNSW vectors
- **14 API sub-routers** — all project-scoped endpoints auth-protected

---

## Questions?

1. **How does the system work?** → Read CURRENT-STATE.md
2. **What's the pipeline?** → Read STAGE-FLOW.md
3. **How do I run it?** → Read COMMANDS.md
4. **What's next?** → Read ROADMAP.md
5. **API docs?** → Auto-generated at `http://localhost:8000/docs`

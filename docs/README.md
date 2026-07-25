# Documentation Index

**Last Updated**: 2026-07-25  
**Master Document**: `CURRENT-STATE.md` (authoritative system description)

---

## Quick Navigation

### 📋 Start Here
- **[CURRENT-STATE.md](CURRENT-STATE.md)** — **AUTHORITATIVE** system description (what's actually implemented)
- **[COMMANDS.md](COMMANDS.md)** — How to set up, run, and test the system
- **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** — System overview (updated 2026-07-25)

### 🏗️ Architecture & Design
- **[STAGE-FLOW.md](STAGE-FLOW.md)** — 12-stage pipeline specification (updated 2026-07-25)
- **[ROADMAP.md](ROADMAP.md)** — Implementation roadmap + what's next (updated 2026-07-25)

### 🔍 Audit Reports (New — 2026-07-25)
- **[AUDIT_EXECUTIVE_SUMMARY.md](AUDIT_EXECUTIVE_SUMMARY.md)** — 1-page quick reference
- **[AUDIT_FINAL_FINDINGS.md](AUDIT_FINAL_FINDINGS.md)** — 7 critical issues found + fixes
- **[AUDIT_TECH_DEBT.md](AUDIT_TECH_DEBT.md)** — 31-issue inventory (critical/high/medium/low)
- **[AUDIT_COMPONENT_INDEX.md](AUDIT_COMPONENT_INDEX.md)** — 52 components status matrix
- **[AUDIT_ARCHITECTURAL.md](AUDIT_ARCHITECTURAL.md)** — Full 6-phase architectural audit

### ⚠️ Known Limitations
- Polling-based frontend (not WebSockets)
- No version pinning (npm `*`, pip no version)
- Single-process only (no horizontal scaling)
- No authentication/RBAC (single-user only)
- Stop signal can't interrupt LLM calls

---

## Document Status

### ✅ Current (Up-to-Date)
| Document | Purpose | Last Updated |
|----------|---------|--------------|
| CURRENT-STATE.md | System description (AUTHORITATIVE) | 2026-07-24 |
| COMMANDS.md | Setup + run + test | 2026-07-24 |
| PROJECT_OVERVIEW.md | System overview | 2026-07-25 (UPDATED) |
| STAGE-FLOW.md | 12-stage pipeline | 2026-07-25 (UPDATED) |
| ROADMAP.md | Implementation roadmap | 2026-07-25 (UPDATED) |
| AUDIT_*.md (5 files) | Architecture audit | 2026-07-25 (NEW) |

### ⚠️ Outdated (Superseded)
| Document | Reason | See Instead |
|----------|--------|-------------|
| PROJECT_OVERVIEW.md (old version) | Described system as "lightweight prototype" | Updated version ✅ |
| STAGE-FLOW.md (old version) | Listed 11 stages with "Planner" | Updated version ✅ |
| ROADMAP.md (old version) | Phase 1 talks about "fix retry loop" | Updated version ✅ |
| AGENT-PROFILES.md | Planning doc, not current | CURRENT-STATE.md |
| ARTIFACT-SCHEMAS.md | Planning doc, not current | CURRENT-STATE.md |
| LEARNING-SYSTEM.md | Planning doc, not current | CURRENT-STATE.md |
| SAFETY-POLICY.md | Planning doc, not current | CURRENT-STATE.md |
| execution-log.md | Old execution tracking | CURRENT-STATE.md |
| repository-certification.md | Old planning | CURRENT-STATE.md |

---

## For Different Audiences

### 👤 New Developer
1. Read: **COMMANDS.md** (setup instructions)
2. Read: **PROJECT_OVERVIEW.md** (system overview)
3. Read: **STAGE-FLOW.md** (12-stage pipeline)
4. Explore: backend/app/ (code structure)
5. Run tests: `python -m pytest tests/ -q`

### 🏢 Product Manager
1. Read: **PROJECT_OVERVIEW.md** (1 page)
2. Read: **AUDIT_EXECUTIVE_SUMMARY.md** (1 page)
3. Discuss: Series A readiness (see AUDIT_FINAL_FINDINGS.md)

### 🛠️ Operations / DevOps
1. Read: **COMMANDS.md** (setup, health checks)
2. Read: **CURRENT-STATE.md** § 6 (frontend architecture) + § 7 (memory system)
3. Plan: Deployment (see ROADMAP.md for monitoring/alerting roadmap)

### 🏛️ Architect / CTO
1. Read: **AUDIT_ARCHITECTURAL.md** (full audit)
2. Read: **AUDIT_TECH_DEBT.md** (31 issues, prioritized)
3. Read: **ROADMAP.md** (what's next)

### 🧪 QA / Testing
1. Read: **COMMANDS.md** (run tests)
2. Read: **CURRENT-STATE.md** § 3 (12-stage pipeline)
3. Explore: backend/tests/ (test suite)

---

## Series A Readiness

**Current Status**: ⚠️ Not ready (7 critical issues)  
**Timeline to Ready**: 2-3 weeks (with 2-3 engineers)  
**Key Documents**:
- **AUDIT_FINAL_FINDINGS.md** — What needs to be fixed
- **AUDIT_TECH_DEBT.md** — Detailed issue inventory
- **ROADMAP.md** — Week-by-week fix plan

---

## Version History

| Version | Date | Status | Key Changes |
|---------|------|--------|-------------|
| 1.1 | 2026-07-25 | Production (with audit findings) | 12-stage pipeline complete; 7 critical issues found |
| 1.0 | 2026-07-24 | Shipped | Initial release |

---

## Document Maintenance

- **CURRENT-STATE.md** — Authoritative system description (update when implementation changes)
- **COMMANDS.md** — Update when setup/run process changes
- **ROADMAP.md** — Update monthly with progress
- **AUDIT_*.md** — Update after audit completion (2026-07-25)
- Old planning docs — Archive to `archived/` (future cleanup)

---

## Related Resources

- **GitHub Issues**: (link to issues tracker for bugs/features)
- **Slack Channel**: #ai-devos-dev
- **Design Docs**: See `/research/` folder for research artifacts
- **API Docs**: Auto-generated from FastAPI at `http://localhost:8000/docs`

---

## Questions?

1. **How does the system work?** → Read CURRENT-STATE.md
2. **What are the critical issues?** → Read AUDIT_FINAL_FINDINGS.md
3. **What's the 12-stage pipeline?** → Read STAGE-FLOW.md
4. **How do I run it?** → Read COMMANDS.md
5. **What's next?** → Read ROADMAP.md


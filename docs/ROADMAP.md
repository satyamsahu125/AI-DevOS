# Implementation Roadmap

**Last Updated**: 2026-07-25  
**Current Version**: 1.1 (Production-Grade)  
**Audit Status**: 7 Critical, 7 High, 10 Medium issues found (see AUDIT_TECH_DEBT.md)

---

## What's Implemented ✅

### Phase 0 — Core Pipeline (COMPLETE)
- ✅ 12-stage pipeline fully wired and operational
- ✅ All 14 agents implemented (12 core + 2 auxiliary)
- ✅ All 14 action classes (one per stage)
- ✅ Three-tier review system (AUTO_FIX/ASK_HUMAN/FLAG)
- ✅ Real code generation (one LLM call per file)
- ✅ Crash-safe resume via checkpoints
- ✅ Learning loop + trajectory recording
- ✅ Knowledge embedding + semantic search
- ✅ LLM provider abstraction (Ollama + Bedrock)
- ✅ Project isolation + workspace management
- ✅ File validation + safety policy
- ✅ API layer (10 routes)
- ✅ 42 test files, 194 tests passing

### Phase 1 — Bug Fixes (MOSTLY COMPLETE)
- ✅ Retry loop wired in WorkflowEngine
- ✅ All agents connected to LLMManager
- ✅ MemoryManager fully integrated
- ✅ Real LLM calls (not echoing prompts)
- ✅ Context builder reading actual memory
- ✅ Logging added to major components
- ⚠️ Silent exception swallowing (4 files still need fixing — CRITICAL)
- ⚠️ Direct agent instantiation (still using direct construction — CRITICAL)
- ⚠️ Database files in git (still tracked — CRITICAL)

### Phase 2 — Structured Outputs (COMPLETE)
- ✅ Action layer implemented (LLMAction base class)
- ✅ Pydantic schema validation per stage
- ✅ JSON extraction + repair logic
- ✅ Schema-specific reviewer rules

### Phase 3 — Memory & Learning (COMPLETE)
- ✅ Artifact history (every attempt saved)
- ✅ Trajectory recording (approved + rejected)
- ✅ Knowledge embedding (semantic search)
- ✅ Lesson storage (human-readable insights)
- ✅ Design memory (durable across run)
- ✅ Checkpoint manager (crash recovery)
- ⚠️ Per-project trajectory tracking missing project_id column (HIGH priority)

### Phase 4 — Code Generation (COMPLETE)
- ✅ Backend file generation (one per LLM call)
- ✅ Frontend file generation (one per LLM call)
- ✅ File validation (Python/JavaScript syntax)
- ✅ Path sanitization (no `..` traversal)
- ✅ Auto-generated manifests (package.json, requirements.txt)
- ⚠️ Version pinning not implemented (CRITICAL)

### Phase 5 — Deployment & Operations (COMPLETE)
- ✅ Health checks (/health, /ready)
- ✅ Live output streaming (polling-based)
- ✅ Project download (ZIP + run instructions)
- ✅ LLM provider switching (runtime, no restart)
- ✅ Database persistence (SQLite)
- ⚠️ No monitoring/alerting (not implemented)
- ⚠️ No rate limiting (not implemented)

---

## Critical Issues Found (Series A Blockers)

### Week 1 Priority (Must Fix Before Series A)

**7 Critical Issues** (20 hours to fix):

1. **Silent Exception Swallowing** (4 files)
   - Files: workflow.py, documentation_builder.py, project_reader.py, manager.py
   - Issue: `except Exception: pass` masks production failures
   - Fix: Add logging + explicit error handling

2. **Direct Agent Instantiation** (architecture violation)
   - File: workflow/manager.py:51-52
   - Issue: Uses direct construction instead of factory pattern
   - Fix: Use AgentFactory for all agent creation

3. **Database Files in Git**
   - Files: memory/*.db, memory/*.hnsw
   - Issue: Binary diffs, unmergeable conflicts
   - Fix: `git rm --cached *.db` + update .gitignore

4. **Duplicate MemoryManager Classes** (name collision)
   - Files: memory_manager.py vs manager.py
   - Issue: Two classes with same name, different interfaces
   - Fix: Rename one (MemoryOrchestrator or MemoryStore)

5. **Architect Action Stub Fallback** (data quality)
   - File: actions/write_architecture.py:26-50
   - Issue: Fallback returns hardcoded fake architecture
   - Fix: Raise SchemaValidationError instead

6. **Version Pinning Not Implemented** (reproducibility)
   - File: workspace/dependency_detector.py
   - Issue: Generated manifests use `*` for npm, no version for pip
   - Fix: Extract versions from imports, pin manifests

7. **Hardcoded Database Paths** (brittle configuration)
   - File: execution/safety_policy.py:15-16
   - Issue: Paths relative to file location
   - Fix: Use environment variables

**Timeline**: 2-3 weeks (with 2-3 engineers) → System ready for Series A

---

## High Priority (Next Sprint)

**7 High Issues** (15 hours to fix):

1. **Empty Directory** (dead code) — backend/app/artifacts/
2. **Unused Interface** — shared/interfaces/memory.py
3. **Dynamic Imports** — api/workflow.py
4. **Per-Project Trajectory** — missing project_id column
5. **Checkpoint Cleanup** — no garbage collection
6. **Stop Signal** — can't interrupt LLM calls
7. **Large Classes (SRP)** — 5 classes > 350 LOC

---

## Medium Priority (Polish Phase)

**10 Medium Issues** (40 hours to fix):

- Frontend test coverage (add Vitest setup)
- Integration tests (E2E test suite)
- Authentication/RBAC (for multi-user)
- Polling frontend → WebSockets
- Rate limiting on API
- Exception handling audit
- Checkpoint serialization versioning
- Cost tracking per project
- Polling intervals configurable
- Workflow visualization export

---

## Future Roadmap (After Series A)

### Month 2: Production Hardening
1. **Version Pinning** (4-6 hours)
   - Extract versions from imports
   - Generate requirements.txt with pinned versions
   - Generate package-lock.json / poetry.lock

2. **Per-Project Analytics** (2-3 hours)
   - Add project_id to trajectories table
   - Query per-project success rates
   - Dashboard showing project progress

3. **Monitoring & Alerting** (8-10 hours)
   - Add Prometheus metrics
   - Set up Grafana dashboard
   - Alert rules for failed stages

4. **Additional Providers** (6-8 hours)
   - Azure OpenAI support
   - Anthropic Claude API support
   - Cohere/Llama integration

### Month 3-4: Scaling Foundation
1. **Async Execution** (12-16 hours)
   - Refactor to asyncio
   - Thread pool for LLM calls
   - Concurrent project execution

2. **Distributed Cache** (8-10 hours)
   - Redis integration
   - Shared memory stores
   - Cache invalidation logic

3. **Database Portability** (10-12 hours)
   - PostgreSQL support (in addition to SQLite)
   - Multi-instance coordination
   - Schema migrations

### Month 5-6: Enterprise Features
1. **Authentication & RBAC** (12-16 hours)
   - JWT token auth
   - User-scoped projects
   - Admin dashboard

2. **Horizontal Scaling** (16-20 hours)
   - Message queue (Celery/RQ)
   - Multiple backend instances
   - Load balancer configuration

3. **Multi-Model Comparison** (8-10 hours)
   - A/B test feature
   - Run same stage with 2 models
   - Compare outputs side-by-side

4. **Human-in-the-Loop** (12-16 hours)
   - True pause on ASK_HUMAN finding
   - Manual approval workflow
   - Timeout after N days

### Month 7+: Advanced Features
1. **Selective Stage Retry** (6-8 hours)
   - Re-run one failed stage
   - Don't re-run all 12 stages

2. **Model Parameter Tuning** (4-6 hours)
   - Temperature, top_p per stage
   - Runtime configuration UI

3. **Batch Project Generation** (8-10 hours)
   - Queue multiple projects
   - Concurrent execution

4. **Workflow Visualization Export** (4-6 hours)
   - SVG/PNG diagram export
   - Mermaid diagram generation

---

## Not Planned (Out of Scope)

❌ **Web3/Blockchain Integration** — No plans  
❌ **Mobile App** — Focus on web first  
❌ **Multi-Language LLM** — English-first, expand later  
❌ **On-Premise Installation** — Cloud-first for now  
❌ **Custom Model Training** — Use existing models only  

---

## Success Metrics

### Series A Gate (Month 1)
- [ ] 0 critical issues (7 found → all fixed)
- [ ] 194 tests passing + new tests for fixes
- [ ] Code audit clean (no silent failures)
- [ ] Load tested at 10+ concurrent projects
- [ ] Production deployment docs complete

### Series A+3 Months
- [ ] Version pinning working
- [ ] Per-project analytics dashboard
- [ ] Monitoring/alerting operational
- [ ] 2+ additional LLM providers
- [ ] 50+ test files, 300+ tests

### Series A+6 Months
- [ ] Async execution working
- [ ] PostgreSQL support
- [ ] Redis cache deployed
- [ ] Authentication/RBAC live
- [ ] Horizontal scaling validated

### Series A+12 Months
- [ ] Support 10k+ concurrent projects
- [ ] Multi-region deployment
- [ ] Enterprise features complete
- [ ] 80%+ test coverage
- [ ] Zero P0 issues in production

---

## Effort Estimates

| Phase | Work | Effort | Timeline |
|-------|------|--------|----------|
| Critical Fixes | Silent exceptions, DI, database files, etc. | 20 hours | 2-3 weeks |
| High Priority | Analytics, cleanup, tests | 15 hours | 1 week |
| Medium Priority | Hardening, frontend tests, E2E | 40 hours | 2-3 weeks |
| Future (Months 2-4) | Async, Redis, Postgres, auth | 80+ hours | 4-6 weeks |
| Future (Months 5-12) | Scaling, enterprise features | 100+ hours | 3+ months |

**Total to Series A-Ready**: ~75 hours (3 engineers × 2-3 weeks)

**Total to Production-Ready**: ~250+ hours (ongoing)

---

## Decision Points

### Go/No-Go for Series A (Week 2)
- [ ] All 7 critical issues fixed?
- [ ] Tests passing?
- [ ] Code audit clean?
- [ ] Load test OK?
→ **Decision**: Proceed or extend 1 more week?

### Go/No-Go for GA (Month 3)
- [ ] Version pinning done?
- [ ] Monitoring/alerting live?
- [ ] Auth/RBAC implemented?
- [ ] Additional providers working?
→ **Decision**: Launch to early customers?

### Go/No-Go for Enterprise (Month 6)
- [ ] Async execution working?
- [ ] PostgreSQL production-tested?
- [ ] Horizontal scaling validated?
- [ ] Enterprise SLA requirements met?
→ **Decision**: Launch enterprise tier?

---

## For Development Team

1. **Week 1-2**: Fork + branch for critical fixes
2. **Week 3**: Code review + merge to main
3. **Week 4**: Re-audit + proceed with Series A
4. **Month 2-4**: High-priority features
5. **Month 5+**: Scaling + enterprise features

See `AUDIT_TECH_DEBT.md` for detailed issue breakdown and fix guidance.


# Technical Debt & Issue Inventory

**Audit Date**: 2026-07-25  
**Total Issues Found**: 31  
**Critical**: 7  |  **High**: 7  |  **Medium**: 10  |  **Low**: 7

---

## 🔴 CRITICAL ISSUES (MUST FIX BEFORE SERIES A)

### 1. Silent Exception Swallowing in 4 Files

**Severity**: 🔴 CRITICAL  
**Files**:
- `backend/app/api/workflow.py:122-123`
- `backend/app/prompt/documentation_builder.py:131`
- `backend/app/execution/project_reader.py:129`
- `backend/app/workspace/manager.py:219`

**Pattern**: `except Exception: pass` with no logging

**Impact**: Production failures go completely undetected

**Fix**: Add logging + explicit error handling

**Effort**: LOW (2-3 hours)  
**Blocker**: YES

---

### 2. Direct Agent Instantiation — Architecture Violation

**Severity**: 🔴 CRITICAL  
**File**: `backend/app/workflow/manager.py:51-52`

**Issue**: `self.backend_agent = BackendDeveloperAgent()` instead of factory pattern

**Impact**: Cannot test with mocks; violates dependency inversion

**Fix**: Use AgentFactory for all agent creation

**Effort**: MEDIUM (3-4 hours)  
**Blocker**: YES

---

### 3. Database Files Tracked in Git

**Severity**: 🔴 CRITICAL  
**Files**:
- `backend/app/memory/knowledge.db`
- `backend/app/memory/knowledge.hnsw`
- `backend/app/memory/learning.db`
- `backend/app/memory/lessons.db`
- `backend/app/memory/memory.db`

**Issue**: Binary diffs on every test run; unmergeable conflicts

**Fix**: `git rm --cached *.db` + update .gitignore

**Effort**: LOW (1 hour)  
**Blocker**: YES

---

### 4. Duplicate MemoryManager Classes — Name Collision

**Severity**: 🔴 CRITICAL  
**Files**:
- `backend/app/memory/memory_manager.py` (orchestrator)
- `backend/app/memory/manager.py` (simple store)

**Issue**: Two classes with same name, different interfaces; causes confusion

**Impact**: Wrong manager used; testing nightmare

**Fix**: Rename one class (MemoryOrchestrator or MemoryStore)

**Effort**: MEDIUM (3-4 hours)  
**Blocker**: YES

---

### 5. WriteArchitectureAction Stub Fallback

**Severity**: 🔴 CRITICAL  
**File**: `backend/app/actions/write_architecture.py:26-50`

**Issue**: Falls back to hardcoded default architecture if LLM parse fails

**Impact**: Masks parse errors; produces fake architecture

**Fix**: Raise SchemaValidationError instead of fallback

**Effort**: LOW (1 hour)  
**Blocker**: YES

---

### 6. Version Pinning Not Implemented

**Severity**: 🔴 CRITICAL  
**File**: `backend/app/workspace/dependency_detector.py`

**Issue**: Generated manifests use `*` (npm) and no version (pip)

**Impact**: Builds not reproducible

**Fix**: Extract versions from imports; pin manifests

**Effort**: HIGH (4-6 hours)  
**Blocker**: YES

---

### 7. ProjectManager DI Violation (FIXED)

**Status**: ✅ **FIXED** in this session

---

## 🟠 HIGH PRIORITY ISSUES (NEXT SPRINT)

### 8. Hardcoded Database Paths — Brittle

**Severity**: 🟠 HIGH  
**File**: `backend/app/execution/safety_policy.py:15-16`

**Issue**: Path relative to file location; breaks if file moves

**Fix**: Use environment variables for paths

**Effort**: LOW (1-2 hours)  
**Blocker**: NO

---

### 9. Empty Directory — Dead Code

**Severity**: 🟠 HIGH  
**Path**: `backend/app/artifacts/` (empty, alongside `/artifact/`)

**Action**: Delete directory

**Effort**: LOW (5 mins)  
**Blocker**: NO

---

### 10. Unused Interface Definition

**Severity**: 🟠 HIGH  
**File**: `backend/app/shared/interfaces/memory.py`

**Issue**: NEVER IMPORTED OR USED (dead contract)

**Action**: Delete or document as "planned"

**Effort**: LOW (5 mins)  
**Blocker**: NO

---

### 11. Dynamic Imports in Runtime Code

**Severity**: 🟠 HIGH  
**File**: `backend/app/api/workflow.py:82, 86, 115`

**Issue**: Imports inside functions instead of module level

**Impact**: Defeats static analysis; PEP 8 violation

**Fix**: Move all imports to module top

**Effort**: LOW (1 hour)  
**Blocker**: NO

---

### 12. Per-Project Trajectory Tracking Missing

**Severity**: 🟠 HIGH  
**File**: `backend/app/memory/learning_loop.py:70-89`

**Issue**: Trajectories table has **no `project_id` column**

**Impact**: Can't query per-project success rates

**Recommendation**: Add column + create index

**Effort**: MEDIUM (2-3 hours)  
**Blocker**: NO

---

### 13. Checkpoint Accumulation (No Cleanup)

**Severity**: 🟠 HIGH  
**File**: `backend/app/session/checkpoint.py`

**Issue**: Checkpoint files never deleted, accumulate indefinitely

**Impact**: Storage bloat on long-running projects

**Fix**: Delete checkpoints > 7 days old

**Effort**: LOW (1-2 hours)  
**Blocker**: NO

---

### 14. No True Stop During LLM Call

**Severity**: 🟠 HIGH  
**File**: `backend/app/workflow/engine.py`

**Issue**: Can't interrupt in-flight LLM calls (blocking HTTP)

**Impact**: User must wait 30+ seconds for provider response

**Fix**: Thread-based execution or async

**Effort**: HIGH (6-8 hours)  
**Blocker**: MAYBE

---

## 🟡 MEDIUM PRIORITY ISSUES (POLISH)

### 15-17. Large Classes Violating Single Responsibility (5 classes)

| File | LOC | Issue |
|------|-----|-------|
| workflow/engine.py | 436 | Too many responsibilities |
| review/reviewer.py | 401 | Too many responsibilities |
| workflow/manager.py | 380 | Too many responsibilities |
| memory/memory_repository.py | 350 | Too many responsibilities |
| storage/storage_adapter.py | 290 | Too many responsibilities |

**Fix**: Extract into smaller classes (SRP)

**Effort**: MEDIUM (8-10 hours)

---

### 18. Frontend Test Coverage Low

**Issue**: No visible test files for frontend

**Impact**: Regressions not caught; refactoring risky

**Fix**: Add Vitest setup + component tests

**Effort**: HIGH (20+ hours)

---

### 19. No Integration Tests

**Issue**: Unit tests exist; missing end-to-end integration tests

**Fix**: Add E2E test suite (fixtures, temp DB)

**Effort**: MEDIUM (8-10 hours)

---

### 20. No Authentication / RBAC

**Issue**: No auth anywhere; anyone can create/delete/run any project

**Impact**: Multi-user deployments have zero isolation

**Fix**: Add JWT token auth + user_id scoping

**Effort**: HIGH (6-8 hours)

---

### 21. Polling-Based Frontend Updates

**Issue**: All updates are polling (3-4s latency)

**Impact**: UX latency; unnecessary API load

**Fix**: Migrate to WebSockets

**Effort**: MEDIUM (4-6 hours)

---

### 22. No Rate Limiting on API

**Issue**: No rate limiting; user can spam endpoints

**Impact**: DoS vulnerability

**Fix**: Add slowapi (FastAPI rate limiting)

**Effort**: LOW (2-3 hours)

---

### 23. RuntimeContext/RuntimeResult Unused

**Issue**: Classes defined but not used in execution path

**Impact**: Dead code taking up space

**Fix**: Remove unless part of refactoring plan

**Effort**: LOW (1 hour)

---

### 24. Broad Exception Types Without Recovery

**Count**: 14 files with broad `except Exception:` blocks

**Pattern**: Catch all exceptions but only pass (no logging)

**Fix**: Add explicit error handling + logging

**Effort**: MEDIUM (3-4 hours)

---

## 🟢 LOW PRIORITY ISSUES (NICE-TO-HAVE)

### 25-31. Low Priority Polish

| # | Issue | Effort |
|----|-------|--------|
| 25 | Checkpoint serialization version field | LOW |
| 26 | Memory store query unification | MEDIUM |
| 27 | Cost tracking not per-project | LOW |
| 28 | Polling intervals hardcoded | LOW |
| 29 | No workflow visualization export | MEDIUM |
| 30 | No model comparison UI | HIGH |
| 31 | Documentation outdated (archive old docs) | LOW |

---

## SUMMARY TABLE

| Priority | Count | Effort | Total Hours |
|----------|-------|--------|------------|
| 🔴 Critical | 7 | 0.5-1 hr each | ~20 hours |
| 🟠 High | 7 | 1-4 hrs each | ~20 hours |
| 🟡 Medium | 10 | 2-10 hrs each | ~40 hours |
| 🟢 Low | 7 | 1-3 hrs each | ~15 hours |
| **TOTAL** | **31** | | **~95 hours** |

---

## RISK MATRIX

| Issue | Likelihood | Impact | Risk Level |
|-------|-----------|--------|-----------|
| Architecture fallback masks errors | HIGH | HIGH | 🔴 CRITICAL |
| Version pinning breaks reproducibility | HIGH | MEDIUM | 🟠 HIGH |
| Silent exceptions hide failures | HIGH | HIGH | 🔴 CRITICAL |
| Direct instantiation breaks testing | HIGH | MEDIUM | 🟠 HIGH |
| Database files in git cause conflicts | MEDIUM | MEDIUM | 🟡 MEDIUM |

---

## DECISION MATRIX: WHAT TO FIX BEFORE SHIPPING

| Issue | Must Fix? | Effort | Blocker? |
|-------|-----------|--------|----------|
| Silent exception swallowing | ✅ YES | LOW | YES |
| Direct agent instantiation | ✅ YES | MEDIUM | YES |
| Database files in git | ✅ YES | LOW | YES |
| Duplicate MemoryManager | ✅ YES | MEDIUM | YES |
| Architect fallback | ✅ YES | LOW | YES |
| Version pinning | ✅ YES | HIGH | YES |
| Dynamic imports | ✅ YES | LOW | YES |
| Hardcoded paths | ⚠️ SHOULD | LOW | NO |
| Per-project trajectory | ⚠️ SHOULD | MEDIUM | NO |
| Checkpoint cleanup | ⚠️ SHOULD | LOW | NO |

---

## WEEK-BY-WEEK FIX PLAN

### Week 1: Critical Blocking (20 hours)
1. Remove database files from git (1 hr)
2. Fix silent exception swallowing (3 hrs)
3. Fix architect fallback (1 hr)
4. Refactor direct agent instantiation (4 hrs)
5. Rename duplicate MemoryManager (3 hrs)
6. Delete empty artifacts/ directory (0.5 hr)
7. Move dynamic imports to module level (2 hrs)
8. Move hardcoded paths to config (2 hrs)
9. Documentation (3 hrs)

### Week 2: High Priority (15 hours)
1. Add test coverage (8 hrs)
2. Refactor large classes (SRP) (7 hrs)

### Month 2: Nice-to-Have
1. Version pinning (4-6 hrs)
2. Per-project trajectory (2-3 hrs)
3. Additional tests (5-10 hrs)


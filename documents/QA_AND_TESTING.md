# QA & Testing Audit Document — AI DevOS

> **Source of Truth**: Reverse-engineered directly from `backend/tests/`, `pytest.ini`, `frontend/src/*.test.tsx`, and `frontend/vitest.config.ts`.

---

## 1. Test Architecture Overview

AI DevOS maintains a comprehensive test suite across backend Python modules (`pytest`) and frontend React components (`vitest` + React Testing Library):

- **Backend Test Framework**: `pytest` with `pytest-asyncio` plugin (`pytest.ini`).
- **Frontend Test Framework**: `vitest` with `jsdom` environment (`frontend/vitest.config.ts`).
- **Phase-Based Hardening Verification**: Tests explicitly validate Phase 1 (Docker Sandbox), Phase 2 (Deployable Bug Analysis), Phase 4 (Sprint Gate Gates), Phase 5 (Environment Configuration & E2E Pipeline), and Phase 6 (Alembic, Celery, Prometheus, OTEL).

---

## 2. Backend Test Inventory & Mapping

| Test Module File | Target Subsystem | Scope / Purpose | Status |
| --- | --- | --- | --- |
| `test_phase1_sandbox.py` | Execution Sandbox | Validates Docker sandbox code execution, stdout/stderr capture, and timeout limits | `VERIFIED` |
| `test_phase2_deployable_bug.py` | QA & Bug Analyst | Verifies bug detection, traceback parsing, and failure isolation | `VERIFIED` |
| `test_phase2_sprint_blocked.py` | Sprint Executor | Tests sprint blocking conditions when critical file stages fail | `VERIFIED` |
| `test_phase4_sprint_plan_gate.py` | Reviewer & Gates | Validates gate review pauses at SprintPlan checkpoints | `VERIFIED` |
| `test_phase5_env_config.py` | Configuration Loader | Verifies YAML config overrides and environment variable precedence | `VERIFIED` |
| `test_phase5_sandbox_to_buganalyst_e2e.py` | End-to-End | E2E integration test: Sandbox execution error -> QA failure -> BugAnalyst isolation | `VERIFIED` |
| `test_phase6_alembic.py` | Database Storage | Validates Alembic schema migrations and SQLite database upgrades | `VERIFIED` |
| `test_phase6_celery_dispatch.py` | Task Queue | Tests Celery async task dispatch and Redis fallback handling | `VERIFIED` |
| `test_phase6_db_paths.py` | Storage Adapters | Verifies multi-database path resolution (`auth.db`, `memory.sqlite`, `costs.db`) | `VERIFIED` |
| `test_phase6_middleware.py` | FastAPI Middleware | Verifies API Key auth, RateLimit, and RequestSizeLimit middleware | `VERIFIED` |
| `test_phase6_prometheus.py` | Observability | Tests `/metrics` endpoint format and Prometheus counter increments | `VERIFIED` |
| `test_artifact_stamping.py` | Artifact Subsystem | Tests hash stamping and version tracking on emitted artifacts | `VERIFIED` |
| `test_change_manager_req_version.py` | Change Manager | Verifies requirement version increments upon reviewer rejection | `VERIFIED` |
| `test_change_manager_sprint_stale.py` | Sprint Executor | Validates stale sprint artifact invalidation when requirements change | `VERIFIED` |
| `test_container_intelligence_wiring.py` | DI Container | Tests AIKernel service registration and dependency injection wiring | `VERIFIED` |
| `test_intelligence_layer_wiring.py` | Memory & RAG | Verifies HNSW vector index lookups and SQLite metadata hydration | `VERIFIED` |
| `test_intelligent_retry_engine.py` | Workflow Engine | Verifies stage backoff policies and retry counter limits | `VERIFIED` |
| `test_replanning_router.py` | Replanning Router | Tests target stage rewinding upon rejection or test failure | `VERIFIED` |
| `test_sprint_scoped_memory.py` | Memory Subsystem | Verifies project-id isolation in sprint-scoped memory queries | `VERIFIED` |
| `test_stale_artifact_detection.py` | Workspace | Validates file modification timestamp checking and cache invalidation | `VERIFIED` |

---

## 3. Frontend Test Inventory

| Test File | Component / Module | Scope / Purpose | Status |
| --- | --- | --- | --- |
| `frontend/src/App.test.tsx` | Main Router / App | Verifies initial layout rendering and top-level route switching | `VERIFIED` |
| `frontend/src/pages/LandingPage.test.tsx` | Landing Page | Tests hero section rendering and navigate-to-login CTA buttons | `VERIFIED` |
| `frontend/src/pages/LoginPage.test.tsx` | Login Page | Tests form field validation, authentication error states, and token submit | `VERIFIED` |
| `frontend/src/lib/auth.test.tsx` | Auth Context | Tests JWT token parsing, localStorage persistence, and logout action | `VERIFIED` |

---

## 4. Test Coverage Gaps & Risks

1. **WebSocket Reconnection & Backoff Test Gap**: Current frontend unit tests mock WebSocket connection establish phase but lack test coverage for network drop/reconnect scenarios during live workflow execution.
2. **Multi-Worker Database Lock Concurrency Tests**: While WAL mode is enabled on SQLite databases, unit tests execute single-threaded. High-concurrency writing across multiple Celery workers lacks stress testing.
3. **Live Container Web Preview Tests**: `/api/v1/preview/{id}` lacks automated unit tests covering container port conflict handling.

# Actionable Feature & Engineering Tickets — AI DevOS

> **Audit Baseline**: Actionable engineering tickets derived directly from confirmed code gaps, security findings, missing features, and testing limitations identified during the codebase audit.

---

## Ticket Inventory Summary

| Ticket ID | Priority | Area | Title | Status |
| --- | --- | --- | --- | --- |
| [`FEAT-001`](#feat-001) | **P0** | Security / Sandbox | Replace Host Docker Socket Mount with DinD or Rootless Sandbox | OPEN |
| [`FEAT-002`](#feat-002) | **P0** | Security / Auth | Mandatory JWT Secret Key Environment Enforcement on Startup | OPEN |
| [`FEAT-003`](#feat-003) | **P1** | Security / RAG | Enforce Tenant Metadata Filtering & Secret Scrubbing in HNSW Vector Store | OPEN |
| [`FEAT-004`](#feat-004) | **P1** | Security / API | Default-Deny Policy for API Key Middleware when Unconfigured | OPEN |
| [`FEAT-005`](#feat-005) | **P2** | Frontend / API | Implement Live Web Preview Container Proxy Handler | OPEN |
| [`FEAT-006`](#feat-006) | **P2** | Integration / Git | Implement External Remote Git Push & Sync Capability | OPEN |
| [`FEAT-007`](#feat-007) | **P3** | Testing | Automated E2E WebSocket Reconnection & Stress Test Suite | OPEN |

---

## Ticket Details

### FEAT-001
- **Title**: Replace Host Docker Socket Mount with DinD or Rootless Sandbox
- **Priority**: `P0`
- **Area**: Security / Execution Sandbox
- **Current Behavior**: `docker-compose.yml` mounts `/var/run/docker.sock` directly into the worker container, exposing host-level daemon access.
- **Expected Behavior**: Celery worker runs within an isolated rootless container environment or DinD sidecar without host Docker socket access.
- **Evidence**: `backend/docker-compose.yml` Line 40 (`/var/run/docker.sock:/var/run/docker.sock`).
- **Acceptance Criteria**:
  1. Celery worker container runs Phase 1/5 execution without host socket mount.
  2. Spawns sandboxed code within non-root user namespaces.
  3. Sandbox unit tests (`test_phase1_sandbox.py`) pass cleanly.
- **Dependencies**: Docker Compose v2, rootless container engine.
- **Files/Modules**: `backend/docker-compose.yml`, `backend/app/execution/docker_sandbox.py`.
- **Testing Requirements**: Run `pytest tests/test_phase1_sandbox.py`.
- **Status**: OPEN

---

### FEAT-002
- **Title**: Mandatory JWT Secret Key Environment Enforcement on Startup
- **Priority**: `P0`
- **Area**: Security / Auth
- **Current Behavior**: Missing `JWT_SECRET_KEY` falls back to static string `"dev-secret-key-change-in-production"`.
- **Expected Behavior**: Application initialization fails fast on startup with `ConfigurationException` if `AUTH_ENABLED=true` and `JWT_SECRET_KEY` is default or missing.
- **Evidence**: `backend/app/api/middleware/auth.py`, `backend/app/api/auth.py`.
- **Acceptance Criteria**:
  1. Startup raises `ConfigurationException` when `JWT_SECRET_KEY` is omitted or equal to default string in non-dev mode.
  2. Integration tests verify server refuse-to-start behavior.
- **Dependencies**: None.
- **Files/Modules**: `backend/app/api/middleware/auth.py`, `backend/app/config/`.
- **Testing Requirements**: Add unit test in `test_phase6_middleware.py`.
- **Status**: OPEN

---

### FEAT-003
- **Title**: Enforce Tenant Metadata Filtering & Secret Scrubbing in HNSW Vector Store
- **Priority**: `P1`
- **Area**: Security / Memory & RAG
- **Current Behavior**: `knowledge.hnsw` indexes text embeddings globally without stripping credentials or isolating tenant queries.
- **Expected Behavior**: Secret scrubber removes API keys, JWTs, and passwords before vector indexing; k-NN retrieval filters metadata by project ID when required.
- **Evidence**: `backend/app/memory/hnsw_memory_store.py`, `backend/app/intelligence/`.
- **Acceptance Criteria**:
  1. API keys/secrets are sanitized prior to embedding calculation.
  2. Multi-tenant vector retrieval tests confirm zero context leakage between projects.
- **Dependencies**: `hnswlib`, `sentence-transformers`.
- **Files/Modules**: `backend/app/memory/hnsw_memory_store.py`, `backend/app/learning/`.
- **Testing Requirements**: Add unit test in `test_sprint_scoped_memory.py`.
- **Status**: OPEN

---

### FEAT-004
- **Title**: Default-Deny Policy for API Key Middleware when Unconfigured
- **Priority**: `P1`
- **Area**: Security / API
- **Current Behavior**: `APIKeyMiddleware` passes unauthenticated requests through when `VALID_API_KEYS` is empty.
- **Expected Behavior**: When `AUTH_ENABLED=true`, missing or unconfigured `VALID_API_KEYS` rejects unauthenticated API calls with `401 Unauthorized`.
- **Evidence**: `backend/app/api/middleware/auth.py`.
- **Acceptance Criteria**:
  1. Requests without valid token or key return HTTP 401 when auth is enabled.
- **Dependencies**: None.
- **Files/Modules**: `backend/app/api/middleware/auth.py`.
- **Testing Requirements**: Update `test_phase6_middleware.py`.
- **Status**: OPEN

---

### FEAT-005
- **Title**: Implement Live Web Preview Container Proxy Handler
- **Priority**: `P2`
- **Area**: Frontend / API
- **Current Behavior**: `/api/v1/preview/{id}` returns container port mapping JSON but lacks an HTTP reverse proxy for live hot-reloading iframe previews.
- **Expected Behavior**: Endpoint proxies HTTP requests directly to running preview containers.
- **Evidence**: `backend/app/api/preview.py`, `frontend/src/pages/WorkspacePage.tsx`.
- **Acceptance Criteria**:
  1. Endpoint streams container web server HTML/JS to frontend iframe.
- **Dependencies**: `httpx`.
- **Files/Modules**: `backend/app/api/preview.py`, `frontend/src/pages/WorkspacePage.tsx`.
- **Testing Requirements**: Add integration test in `backend/tests/`.
- **Status**: OPEN

---

### FEAT-006
- **Title**: Implement External Remote Git Push & Sync Capability
- **Priority**: `P2`
- **Area**: Integration / Workspace
- **Current Behavior**: `git_manager.py` manages local project git repositories but lacks remote push functionality (`git push origin main`).
- **Expected Behavior**: Supports pushing generated workspaces to GitHub/GitLab remotes using configured SSH keys or personal access tokens.
- **Evidence**: `backend/app/workspace/git_manager.py`, `backend/app/api/git.py`.
- **Acceptance Criteria**:
  1. API endpoint `POST /api/v1/git/{id}/push` pushes commits to remote Git URL.
- **Dependencies**: `GitPython` or subprocess `git`.
- **Files/Modules**: `backend/app/workspace/git_manager.py`, `backend/app/api/git.py`.
- **Testing Requirements**: Add unit test for git push operations.
- **Status**: OPEN

---

### FEAT-007
- **Title**: Automated E2E WebSocket Reconnection & Stress Test Suite
- **Priority**: `P3`
- **Area**: Testing / Frontend
- **Current Behavior**: Frontend tests mock initial WebSocket connection but do not test reconnection or event drops under load.
- **Expected Behavior**: Automated Vitest suite simulates network disconnects, event backpressure, and state re-sync.
- **Evidence**: `frontend/src/hooks/useWebSocket.ts`.
- **Acceptance Criteria**:
  1. Vitest tests cover connection loss, retry backoff, and event buffer replay.
- **Dependencies**: Vitest.
- **Files/Modules**: `frontend/src/hooks/useWebSocket.ts`.
- **Testing Requirements**: Run `npm test` in `frontend/`.
- **Status**: OPEN

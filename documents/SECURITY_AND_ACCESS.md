# Security & Access Control Audit — AI DevOS

> **Source of Truth**: Extracted directly from code inspection of `backend/app/api/middleware/`, `backend/app/api/auth.py`, `backend/app/execution/docker_sandbox.py`, `backend/app/main.py`, and `backend/data/auth.db`.

---

## 1. Security Architecture Overview

AI DevOS incorporates multi-layered security controls across API access, payload inspection, execution containerization, and data isolation:

1. **Authentication Layer**: Dual support for Bearer JWT Tokens (`python-jose` with `HS256`) and API Key headers (`X-API-Key`).
2. **Password Hashing**: Native `bcrypt` algorithm for password hashing without deprecated `passlib` wrappers.
3. **Payload Inspection**: `RequestSizeLimitMiddleware` rejects payload bodies exceeding 50 KB to prevent prompt context bloat attacks.
4. **Rate Limiting**: `RateLimitMiddleware` restricts project creation to 10 requests per minute per API key/IP.
5. **Execution Isolation**: `DockerSandbox` runs generated code within restricted ephemeral Docker containers with CPU/memory quotas and execution timeouts.
6. **Network Boundaries**: CORS middleware enforces allowed origins (`ALLOWED_ORIGINS` env var).

---

## 2. Security Findings & Risk Classification

### `CRITICAL-01`: Celery Worker Docker Socket Access Risk
- **Severity**: `CRITICAL`
- **Affected File**: `backend/docker-compose.yml` (Line 40), `backend/app/execution/docker_sandbox.py`
- **Description**: The Celery worker container mounts `/var/run/docker.sock` to spawn Phase 1/5 execution containers. If generated python code breaks out of sub-process wrappers or executes arbitrary shell commands on the worker host, an attacker could interact with the host Docker daemon and escalate privileges to root on the host machine.
- **Remediation**: Use rootless Docker, Docker-in-Docker (DinD) sidecar with restricted socket permissions, or gVisor/Kata Container runtimes for Phase 1/5 code execution.

### `HIGH-01`: Hardcoded Fallback JWT Secret Key
- **Severity**: `HIGH`
- **Affected File**: `backend/app/api/middleware/auth.py`, `backend/app/api/auth.py`
- **Description**: If `JWT_SECRET_KEY` is missing from the environment, the system falls back to a static string (`"dev-secret-key-change-in-production"`). An attacker aware of this default can forge admin JWT tokens and bypass authentication entirely.
- **Remediation**: Raise an unrecoverable `ConfigurationException` on startup if `JWT_SECRET_KEY` is not explicitly set when `AUTH_ENABLED=true`.

### `MEDIUM-01`: Open API Key Middleware Fallthrough
- **Severity**: `MEDIUM`
- **Affected File**: `backend/app/api/middleware/auth.py`
- **Description**: When `VALID_API_KEYS` is not set in `.env`, `APIKeyMiddleware` operates in pass-through mode, allowing unauthenticated requests to reach backend API endpoints.
- **Remediation**: Enforce strict default-deny policies in production environments.

### `MEDIUM-02`: Global HNSW Index Cross-Tenant Context Exposure
- **Severity**: `MEDIUM`
- **Affected File**: `backend/app/memory/hnsw_memory_store.py`, `backend/app/intelligence/`
- **Description**: `knowledge.hnsw` and `lessons.sqlite` operate at global scope across all projects. If user prompts or generated code contain proprietary business logic or API keys, those snippets can be embedded and returned during k-NN vector queries in other projects.
- **Remediation**: Implement mandatory secret scrubbing and tenant/project ID metadata filtering prior to indexing vectors into HNSW.

### `LOW-01`: Permissive CORS Default Configurations
- **Severity**: `LOW`
- **Affected File**: `backend/app/main.py` (Line 93)
- **Description**: Default origins fall back to `http://localhost:5173,http://127.0.0.1:5173`.
- **Remediation**: Require `ALLOWED_ORIGINS` to be explicitly configured in non-development deployments.

---

## 3. Security Controls Matrix

| Control Category | Implementation Class / Module | Enforcement Mechanism | Verified Status |
| --- | --- | --- | --- |
| Password Security | `app/api/auth.py` | `bcrypt.hashpw()`, `bcrypt.checkpw()` | `VERIFIED` |
| Token Generation | `app/api/middleware/auth.py` | `jose.jwt.encode(algorithm="HS256")` | `VERIFIED` |
| Payload Size Guard | `app/api/middleware/request_size.py` | Content-Length check (> 50 KB rejected) | `VERIFIED` |
| Rate Limiting | `app/api/middleware/rate_limit.py` | Token bucket (10 project creates/min) | `VERIFIED` |
| Code Execution Isolation | `app/execution/docker_sandbox.py` | Ephemeral Docker container spawn | `VERIFIED` |
| File Syntax Validation | `app/execution/file_validator.py` | `ast.parse()` syntax tree check before write | `VERIFIED` |
| Structured Log Binding | `app/api/middleware/logging_context.py` | Contextual `request_id` & `project_id` | `VERIFIED` |

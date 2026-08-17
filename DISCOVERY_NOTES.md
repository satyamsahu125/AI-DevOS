# Discovery Notes — AI DevOS

Generated: 2026-08-17
Phase 0 complete.

## App Configuration

| Property | Value |
|---|---|
| Frontend URL | http://localhost:5173 |
| Frontend start command | `cd frontend && npm run dev` |
| Backend URL | http://localhost:8000 |
| Backend start command | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app --log-level info` |
| API base path | /api/v1 |
| Health endpoint | GET /health (root-level, no /api/v1 prefix) |
| Auth required | NO — AUTH_ENABLED=false by default (returns anonymous admin user) |
| Human approval gates | NO — REQUIRE_HUMAN_APPROVAL=false by default (pipeline runs end-to-end) |
| LLM provider | AWS Bedrock (configured in backend/.env) |
| LLM model | qwen.qwen3-next-80b-a3b |
| Sandbox | SANDBOX_ENABLED=false in backend/.env (Docker not required) |

## ProjectRequest DTO

```json
{
  "name": "string (required, 1-100 chars, [A-Za-z0-9 _-])",
  "description": "string (required, max 2000 chars)",
  "mode": "\"full\" | \"quick\" (default: \"full\")"
}
```

**IMPORTANT**: There is NO `project_type` field in the API.
Project type is inferred by the pipeline from the description text.
Use descriptive text to indicate technology stack (e.g., "A FastAPI Python REST API..." or "A React Native mobile app...").

## Key API Endpoints

### Projects
| Method | Path | Description |
|---|---|---|
| POST | /api/v1/projects | Create project (no pipeline) |
| POST | /api/v1/projects/create-and-run | Create + start pipeline |
| GET | /api/v1/projects | List projects |
| GET | /api/v1/projects/{id} | Get project status |
| DELETE | /api/v1/projects/{id} | Delete project (204) |
| GET | /api/v1/projects/{id}/files | List generated files |
| GET | /api/v1/projects/{id}/files/{path} | Get file content |
| GET | /api/v1/projects/{id}/sandbox-results | Latest sandbox results |
| GET | /api/v1/projects/{id}/validate | Run validation suite |
| GET | /api/v1/projects/{id}/metrics | LLM cost metrics |

### Project Status Response Shape
```json
{
  "project_id": "string",
  "name": "string",
  "description": "string",
  "status": "not_started | running | complete | failed | paused | stopped",
  "current_stage": "string",
  "stages_completed": ["string", ...],
  "artifacts": [...],
  "workspace_path": "string"
}
```

### Workflow Gates (when REQUIRE_HUMAN_APPROVAL=true)
| Method | Path | Description |
|---|---|---|
| GET | /api/v1/workflow/{id}/gates/current | Get current pending gate |
| POST | /api/v1/workflow/{id}/gates/architecture/approve | Approve architecture |
| POST | /api/v1/workflow/{id}/gates/architecture/revise | Revise architecture |
| POST | /api/v1/workflow/{id}/gates/design/approve | Approve design |
| POST | /api/v1/workflow/{id}/gates/sprint-plan/approve | Approve sprint plan |

### Health
| Method | Path | Description |
|---|---|---|
| GET | /health | Basic health check (returns {"status":"healthy"}) |
| GET | /ready | Readiness probe (checks LLM + DB) |
| GET | /api/v1/health | Same health check via versioned path |

### Memory
| Method | Path | Description |
|---|---|---|
| GET | /api/v1/memory/{project_id} | Get all memory records for project |
| GET | /api/v1/memory/stats | Memory factory stats |

## Frontend Routes
| Route | Page |
|---|---|
| / | Landing page |
| /login | Login page |
| /projects | Projects list (create button here) |
| /projects/:projectId | Workspace / pipeline view |
| /analytics | Analytics |
| /settings | Settings |
| /admin | Admin |

## Existing Test Files

### Backend (pytest — backend/tests/)
46 Python test files covering unit and integration tests.
Notable pre-existing failures known from FIX_LOG:
- `test_sandbox_enabled_default_is_false` — tests old buggy default (B-15 changed it)
- `test_predecessor_truncated` — tests old 1000-char limit (B-10 changed it to 6000)

### Frontend (Vitest — frontend/src/)
- `src/App.test.tsx`
- `src/pages/LandingPage.test.tsx`
- `src/pages/LoginPage.test.tsx`

### Playwright / E2E
**None found.** No playwright.config.ts or e2e/ directory existed.
This test suite is the first Playwright test setup for AI DevOS.

## Playwright Setup
- Node.js: v22.22.3 (confirmed on device)
- Playwright: NOT installed — will install @playwright/test
- Config: `e2e/playwright.config.ts`
- Test directory: `e2e/tests/`

## Critical API Differences from Test Prompt Assumptions
1. No `project_type` field — inferred from description text
2. API prefix is `/api/v1/` not `/api/`
3. `create-and-run` endpoint returns `{id, name, description, status, state}`
4. Status endpoint is `GET /api/v1/projects/{id}` (not a separate `/status` route)
5. No `/api/v1/projects/{id}/status` route — use GET /api/v1/projects/{id}
6. No `/api/v1/memory/store` — knowledge memory API is different
7. No `/api/v1/prompts/preview` route exists (tests guarded with `if (res.ok())`)
8. No `/api/v1/artifacts` route (artifacts are listed in project detail response)

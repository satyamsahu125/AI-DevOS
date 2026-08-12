# API Specification Reference — AI DevOS

> **Source of Truth**: Extracted directly from FastAPI routers in `backend/app/api/` and `router.py`.

---

## 1. Global API Configuration

- **Base URL**: `/api/v1`
- **Authentication**: Bearer JWT (`Authorization: Bearer <token>`) or API Key (`X-API-Key: <key>`).
- **Global Error Format**:
  ```json
  {
    "error_code": "RESOURCE_NOT_FOUND",
    "message": "Project 'prj_123' was not found.",
    "details": {},
    "timestamp": "2026-08-11T22:10:00Z"
  }
  ```

---

## 2. API Endpoints Reference Matrix

| Method | Endpoint | Auth | Request Body / Params | Response Model | Side Effects / State Changes | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/ready` | None | None | `ReadyResponse` | Checks database & LLM health | `IMPLEMENTED` |
| `GET` | `/api/v1/health` | None | None | `HealthStatus` | System health summary | `IMPLEMENTED` |
| `POST` | `/api/v1/auth/register` | None | `UserRegisterRequest` | `TokenResponse` | Creates user in `auth.db` | `IMPLEMENTED` |
| `POST` | `/api/v1/auth/login` | None | `UserLoginRequest` | `TokenResponse` | Authenticates credentials | `IMPLEMENTED` |
| `GET` | `/api/v1/auth/me` | Bearer | None | `UserResponse` | Returns current user profile | `IMPLEMENTED` |
| `GET` | `/api/v1/admin/users` | Bearer (Admin) | `skip`, `limit` | `List[UserResponse]` | Admin user management | `IMPLEMENTED` |
| `POST` | `/api/v1/projects` | Bearer / APIKey | `ProjectCreateRequest` | `ProjectResponse` | Creates project, initializes DB & workspace | `IMPLEMENTED` |
| `GET` | `/api/v1/projects` | Bearer / APIKey | `skip`, `limit` | `List[ProjectResponse]` | Queries project database | `IMPLEMENTED` |
| `GET` | `/api/v1/projects/{id}` | Bearer / APIKey | Path: `id` | `ProjectResponse` | Fetches project state | `IMPLEMENTED` |
| `POST` | `/api/v1/projects/{id}/start` | Bearer / APIKey | Path: `id` | `WorkflowStartResponse` | Dispatches Celery / Background workflow | `IMPLEMENTED` |
| `POST` | `/api/v1/projects/{id}/cancel`| Bearer / APIKey | Path: `id` | `WorkflowStatusResponse` | Revokes Celery task, sets state `CANCELLED` | `IMPLEMENTED` |
| `POST` | `/api/v1/projects/{id}/resume`| Bearer / APIKey | Path: `id` | `WorkflowStatusResponse` | Resumes from latest checkpoint | `IMPLEMENTED` |
| `GET` | `/api/v1/workflow/{id}/status`| Bearer / APIKey | Path: `id` | `WorkflowStatusResponse` | Queries state machine execution status | `IMPLEMENTED` |
| `GET` | `/api/v1/gates/{id}` | Bearer / APIKey | Path: `id` | `GateReviewStatus` | Checks active reviewer gate status | `IMPLEMENTED` |
| `POST` | `/api/v1/gates/{id}/review` | Bearer / APIKey | `ReviewDecisionRequest` | `ReviewResultResponse` | Submits gate decision, triggers change router | `IMPLEMENTED` |
| `GET` | `/api/v1/artifacts/{id}` | Bearer / APIKey | Path: `id`, query `stage` | `List[ArtifactResponse]` | Fetches stage output artifacts | `IMPLEMENTED` |
| `GET` | `/api/v1/files/{id}/tree` | Bearer / APIKey | Path: `id` | `FileTreeResponse` | Lists project workspace files | `IMPLEMENTED` |
| `GET` | `/api/v1/files/{id}/content`| Bearer / APIKey | Path: `id`, query `path` | `FileContentResponse` | Views project file content | `IMPLEMENTED` |
| `GET` | `/api/v1/logs/{id}` | Bearer / APIKey | Path: `id`, query `limit` | `List[LogEntry]` | Fetches structured project logs | `IMPLEMENTED` |
| `GET` | `/api/v1/analytics/costs` | Bearer / APIKey | Path: `id` | `CostSummaryResponse` | Queries token & dollar usage in `costs.db` | `IMPLEMENTED` |
| `GET` | `/api/v1/agents` | Bearer / APIKey | None | `List[AgentInfo]` | Returns registered agent definitions | `IMPLEMENTED` |
| `GET` | `/api/v1/memory/{id}` | Bearer / APIKey | Path: `id` | `MemorySummaryResponse` | Queries memory entries for project | `IMPLEMENTED` |
| `GET` | `/api/v1/preview/{id}` | Bearer / APIKey | Path: `id` | `PreviewStatusResponse` | Returns live container port mappings | `PARTIAL` |
| `POST` | `/api/v1/git/{id}/sync` | Bearer / APIKey | Path: `id` | `GitSyncResponse` | Manages local project git repository | `PARTIAL` |
| `GET` | `/api/v1/intelligence/{id}`| Bearer / APIKey | Path: `id` | `IntelligenceReport` | Queries RAG vector ranker findings | `IMPLEMENTED` |
| `WS` | `/api/v1/ws/{id}` | Optional Query | Path: `id` | WebSocket Stream | Streams real-time logs & stage progress | `IMPLEMENTED` |

---

## 3. WebSocket Event Specification

- **Endpoint**: `ws://<host>:8000/api/v1/ws/{project_id}`
- **Message Types**:
  1. `STAGE_PROGRESS`: Emitted during stage execution (`percent`, `stage_name`, `message`).
  2. `LOG_EMITTED`: Emitted on structured log generation (`log_level`, `module`, `message`).
  3. `GATE_REQUIRED`: Emitted when workflow pauses for reviewer decision (`gate_id`, `stage`).
  4. `WORKFLOW_COMPLETED`: Emitted when project reaches terminal completion.
  5. `WORKFLOW_FAILED`: Emitted on unrecoverable error (`error_message`, `stage`).

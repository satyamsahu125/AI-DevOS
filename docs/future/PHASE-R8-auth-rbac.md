# Phase R8 — Multi-User Auth + RBAC

**Timeline:** Week 10–12  
**Depends on:** R1 (WebSocket auth fix already in place as groundwork)  
**Problem:** Zero access control. Any client with network access to the server sees and controls every project.  
**Outcome:** JWT authentication, per-user project ownership, role-based access (admin/developer/viewer), and rate limiting.

---

## Why This Matters

AI DevOS cannot be used by a team, deployed to a shared server, or opened to multiple users until project isolation exists. Currently, User A's projects are fully visible and modifiable by User B. This is a blocking issue for any non-single-user deployment.

---

## User Model

**New table in `users.db`:**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,          -- UUID
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'developer',  -- admin | developer | viewer
    created_at TEXT NOT NULL,
    last_login TEXT
);
```

**Roles:**
- `admin` — sees all projects, can delete any project, can manage users
- `developer` — creates projects, sees only their own projects, full control
- `viewer` — sees only projects they are explicitly shared on, read-only

---

## Auth Endpoints

### POST /auth/register
```json
{"email": "user@example.com", "password": "..."}
→ {"user_id": "...", "email": "...", "role": "developer"}
```
Password hashed with `bcrypt` (passlib). Never stored in plain text.

### POST /auth/login
```json
{"email": "user@example.com", "password": "..."}
→ {"access_token": "...", "refresh_token": "...", "expires_in": 900}
```
- Access token: JWT, HS256, 15-minute expiry
- Refresh token: opaque UUID, stored in `refresh_tokens` table, 7-day expiry

### POST /auth/refresh
```json
{"refresh_token": "..."}
→ {"access_token": "...", "expires_in": 900}
```

### POST /auth/logout
Invalidates the provided refresh token. Access tokens expire naturally (15 min).

---

## JWT Implementation

**File:** `backend/app/api/middleware/jwt_auth.py`

```python
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = settings.jwt_secret  # Read from env, never hardcoded
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Raises JWTError on invalid or expired token."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
```

**FastAPI dependency:**
```python
async def get_current_user(
    authorization: str = Header(None),
    x_api_key: str = Header(None),  # Backward compat for service accounts
) -> User:
    # Try JWT Bearer first, then X-API-Key for service accounts
    ...
```

---

## Project Ownership

**Modify projects table:** Add `owner_id TEXT REFERENCES users(id)`

**All project queries** (list, get, update, delete, run) must filter by `owner_id = current_user.id` unless `current_user.role == "admin"`.

**Project sharing (optional, Phase R8.1):**
```sql
CREATE TABLE project_shares (
    project_id TEXT,
    user_id TEXT,
    permission TEXT,  -- read | write
    PRIMARY KEY (project_id, user_id)
);
```

**Migration:** Existing projects with no `owner_id` are assigned to a default admin user created during migration.

---

## Rate Limiting

**File:** `backend/app/api/middleware/rate_limit.py`

Use `slowapi` (wraps limits for FastAPI) or a custom sliding-window counter in Redis (post-R10) / in-memory dict (pre-R10):

```
Default limits:
- 60 requests/minute per user (all endpoints)
- 5 pipeline starts/hour per user (POST /projects/{id}/run)
- 100 chat messages/hour per user (POST /projects/{id}/chat)
```

Return `429 Too Many Requests` with `Retry-After` header.

---

## WebSocket Auth Update

**Supersedes BUG-6 fix from R1.** With JWT in place:

```python
@router.websocket("/ws/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(default=""),
):
    try:
        user = decode_token(token)
        # Verify project belongs to user
        if not await project_belongs_to_user(project_id, user["sub"]):
            await websocket.close(code=4003)
            return
    except JWTError:
        await websocket.close(code=4001)
        return
    # ... existing WebSocket logic
```

---

## UI Changes

**New pages:**
- `/login` — email + password form
- `/register` — registration form
- `/settings/account` — change password, view role

**Navigation:**
- User avatar/email in top-right with logout option
- Projects filtered to current user's projects automatically
- Admin badge shown for admin users with link to `/admin/users`

**Admin panel (basic):**
- `/admin/users` — list all users, change role, delete user
- `/admin/projects` — list all projects across all users

---

## Security Notes

- JWT secret must be in `.env` as `JWT_SECRET_KEY` — never hardcoded
- Use `secrets.compare_digest` for constant-time token comparison
- Bcrypt cost factor ≥ 12
- Refresh tokens invalidated on logout — store in `refresh_tokens(token_hash, user_id, expires_at, invalidated)` table
- Never log passwords or tokens in any log output
- CORS: restrict allowed origins to the frontend domain in production

---

## Exit Criteria

- [ ] `POST /auth/register` + `POST /auth/login` work end-to-end
- [ ] Unauthenticated request to `GET /projects` returns `401`
- [ ] User A cannot access User B's project via any endpoint (returns 403)
- [ ] WebSocket connection rejected with code 4001 on invalid token
- [ ] Rate limiting returns 429 after 60 req/min
- [ ] `/login` page in frontend, successful login redirects to dashboard
- [ ] Existing projects migrated to default admin user (no data loss)
- [ ] JWT secret in `.env`, not in source code
- [ ] All R1–R7 exit criteria still passing

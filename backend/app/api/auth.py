"""R8 — Auth API endpoints.

Provides:
  POST /auth/register   — create a new user account
  POST /auth/login      — email+password → access + refresh tokens
  POST /auth/refresh    — exchange refresh token for new access token
  POST /auth/logout     — invalidate the provided refresh token
  GET  /auth/me         — return current user info from JWT
  POST /auth/change-password — change own password
  GET  /admin/users     — list all users (admin only)
  PUT  /admin/users/{user_id}/role — change a user's role (admin only)
  DELETE /admin/users/{user_id}   — delete a user (admin only)

Security:
- Passwords never logged or returned in any response
- Refresh tokens stored as SHA-256 hashes in DB
- All admin endpoints require role="admin" via require_role()
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from .middleware.jwt_auth import (
    AUTH_ENABLED,
    create_access_token,
    get_current_user,
    require_role,
)
from ..db.users import get_user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "developer"  # admin can set different role


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(body: RegisterRequest) -> dict:
    """Register a new user. Role defaults to 'developer'."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTH_ENABLED=false — set AUTH_ENABLED=true in .env to enable multi-user auth",
        )
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if body.role not in ("admin", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role: must be admin|developer|viewer")

    store = get_user_store()
    try:
        user = store.create_user(body.email, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info("[auth] user registered: email=%s role=%s", user.email, user.role)
    return {"user_id": user.id, "email": user.email, "role": user.role}


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    """Authenticate with email + password. Returns access + refresh tokens."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTH_ENABLED=false — auth endpoints are not active",
        )

    store = get_user_store()
    user = store.verify_password(body.email, body.password)
    if not user:
        logger.warning("[auth] login failed: email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id, user.role)
    refresh_token = store.create_refresh_token(user.id)
    logger.info("[auth] login success: email=%s role=%s", user.email, user.role)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "expires_in": 900,  # 15 min in seconds
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest) -> dict:
    """Exchange a valid refresh token for a new access token."""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="AUTH_ENABLED=false")

    store = get_user_store()
    user = store.validate_refresh_token(body.refresh_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token = create_access_token(user.id, user.role)
    return {"access_token": access_token, "token_type": "bearer", "expires_in": 900}


@router.post("/logout")
async def logout(body: LogoutRequest) -> dict:
    """Invalidate a refresh token (logout). Access token expires naturally."""
    if not AUTH_ENABLED:
        return {"status": "ok"}

    store = get_user_store()
    store.invalidate_refresh_token(body.refresh_token)
    return {"status": "ok"}


@router.get("/me")
async def get_me(user=Depends(get_current_user)) -> dict:
    """Return current user info from the JWT."""
    if not AUTH_ENABLED:
        return {"user_id": "anonymous", "role": "admin", "auth_enabled": False}
    store = get_user_store()
    db_user = store.get_by_id(user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": db_user.id,
        "email": db_user.email,
        "role": db_user.role,
        "created_at": db_user.created_at,
        "last_login": db_user.last_login,
    }


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user=Depends(get_current_user),
) -> dict:
    """Change own password. Requires current password for verification."""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="AUTH_ENABLED=false")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    store = get_user_store()
    db_user = store.get_by_id(user.id)
    if not db_user or not store.verify_password(db_user.email, body.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    new_hash = pwd_ctx.hash(body.new_password)
    # Use the public UserStore method — never access _conn directly from outside
    # the store.  Direct _conn access bypasses the store's connection-lifecycle
    # discipline and races with concurrent requests on the same SQLite handle.
    store.change_password(user.id, new_hash)
    # Invalidate all refresh tokens so existing sessions must re-login
    store.invalidate_all_for_user(user.id)
    logger.info("[auth] password changed: user_id=%s", user.id)
    return {"status": "ok", "message": "Password changed. Please log in again."}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@admin_router.get("/users", dependencies=[Depends(require_role("admin"))])
async def list_users() -> dict:
    """List all users (admin only)."""
    store = get_user_store()
    return {"users": store.list_users()}


@admin_router.put("/users/{user_id}/role", dependencies=[Depends(require_role("admin"))])
async def set_user_role(user_id: str, role: str) -> dict:
    """Change a user's role (admin only). role must be admin|developer|viewer."""
    if role not in ("admin", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    store = get_user_store()
    updated = store.update_role(user_id, role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "role": role}


@admin_router.delete("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def delete_user(user_id: str) -> dict:
    """Delete a user and all their refresh tokens (admin only)."""
    store = get_user_store()
    deleted = store.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted", "user_id": user_id}

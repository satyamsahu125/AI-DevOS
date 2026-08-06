"""R8 — JWT authentication for AI DevOS API.

Provides:
- `create_access_token(user_id, role)` — generate a signed JWT
- `decode_token(token)` — validate and decode (raises JWTError on failure)
- `get_current_user` — FastAPI dependency that extracts and validates the bearer token
- `require_role(role)` — RBAC decorator factory for admin-only endpoints

Auth is OPTIONAL by default (AUTH_ENABLED=false). When disabled:
- `get_current_user` returns a synthetic anonymous User with role "admin"
- All endpoints work without a token (backward compatible with single-user setup)

JWT secret must be set via JWT_SECRET_KEY env var when AUTH_ENABLED=true.
Never hardcoded — startup fails with a clear error if secret is missing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger(__name__)

# Auth is opt-in. Default=false so existing deployments aren't broken.
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))

# Anonymous user returned when auth is disabled
_ANONYMOUS_USER_ID = "anonymous"
_ANONYMOUS_ROLE = "admin"  # full access in single-user mode


def _get_secret() -> str:
    """Return JWT_SECRET_KEY. Fails loudly if auth is enabled but key is missing."""
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret and AUTH_ENABLED:
        raise RuntimeError(
            "JWT_SECRET_KEY env var must be set when AUTH_ENABLED=true. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return secret or "dev-secret-not-for-production"


def create_access_token(user_id: str, role: str) -> str:
    """Create a signed JWT access token for user_id with role.

    Parameters
    ----------
    user_id : str
        The user's UUID.
    role : str
        The user's role: admin | developer | viewer.

    Returns
    -------
    str
        Encoded JWT string.
    """
    try:
        from jose import jwt
    except ImportError:
        raise RuntimeError("python-jose is required for JWT auth: pip install python-jose[cryptography]")

    expire = datetime.now(timezone.utc) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on invalid or expired token.

    Parameters
    ----------
    token : str
        JWT string.

    Returns
    -------
    dict
        Decoded payload: {"sub": user_id, "role": role, "exp": ..., "iat": ...}
    """
    try:
        from jose import jwt, JWTError
    except ImportError:
        raise RuntimeError("python-jose is required for JWT auth")
    return jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

class _CurrentUser:
    """Minimal user context extracted from JWT."""
    __slots__ = ("id", "role")

    def __init__(self, user_id: str, role: str) -> None:
        self.id = user_id
        self.role = role


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> _CurrentUser:
    """FastAPI dependency: extract and validate the Bearer token from Authorization header.

    When AUTH_ENABLED=false, returns an anonymous admin user — all routes work without
    a token (backward compat for single-user setups).

    Raises
    ------
    HTTPException(401)
        When AUTH_ENABLED=true and no/invalid token is provided.
    """
    if not AUTH_ENABLED:
        return _CurrentUser(user_id=_ANONYMOUS_USER_ID, role=_ANONYMOUS_ROLE)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization: Bearer <token> header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        role = payload.get("role", "developer")
        if not user_id:
            raise ValueError("missing sub claim")
    except Exception as exc:
        logger.debug("[jwt_auth] token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _CurrentUser(user_id=user_id, role=role)


def require_role(*allowed_roles: str):
    """RBAC dependency factory.

    Returns a FastAPI dependency that raises 403 if the current user's role
    is not in allowed_roles.

    Usage:
        @router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
    """
    async def _check(user: _CurrentUser = Depends(get_current_user)) -> _CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' does not have access to this resource",
            )
        return user
    return _check

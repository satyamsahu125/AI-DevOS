"""R8 — User store: users + refresh_tokens tables backed by SQLite.

Security design:
- Passwords hashed with bcrypt (cost factor 12) via passlib.
- Refresh tokens stored as SHA-256 hashes — the plain token is never persisted.
- Token invalidation is per-token (logout invalidates the specific refresh token used).
- Existing single-user deployments are unaffected: when AUTH_ENABLED=false,
  none of this code is exercised.

Database file: AUTH_DB_PATH env var (default: data/auth.db)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("AUTH_DB_PATH", "data/auth.db"))

# Bcrypt rounds — NIST recommends >= 10; we use 12 for security margin.
_BCRYPT_ROUNDS = 12


def _get_pwd_context():
    """Lazy import passlib — only required when auth is enabled."""
    from passlib.context import CryptContext
    return CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=_BCRYPT_ROUNDS)


@dataclass(slots=True)
class User:
    """A registered AI DevOS user."""
    id: str
    email: str
    hashed_password: str
    role: str  # admin | developer | viewer
    created_at: str
    last_login: Optional[str]


class UserStore:
    """Manages users and refresh_tokens tables in SQLite.

    Thread-safe via SQLite's WAL mode (single writer, multiple readers).
    Uses check_same_thread=False — callers must not share connections across threads
    (each call should use the shared _conn but SQLite handles concurrent reads fine).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()
        self._ensure_admin()
        logger.info("[UserStore] initialized at %s", self._db_path)

    def _ensure_schema(self) -> None:
        """Create tables on first run."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'developer',
                created_at TEXT NOT NULL,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                expires_at TEXT NOT NULL,
                invalidated INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
        """)
        self._conn.commit()

    def _ensure_admin(self) -> None:
        """Create a default admin user on first run if no users exist.

        Credentials: admin@devos.local / admin (MUST be changed via /auth/change-password).
        Logs a prominent warning so the operator changes it.
        """
        count = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            default_pwd = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
            pwd_ctx = _get_pwd_context()
            hashed = pwd_ctx.hash(default_pwd)
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                "INSERT INTO users (id, email, hashed_password, role, created_at) VALUES (?,?,?,?,?)",
                (str(uuid4()), "admin@devos.local", hashed, "admin", now),
            )
            self._conn.commit()
            logger.warning(
                "[UserStore] default admin created: email=admin@devos.local password=%s — "
                "CHANGE THIS IMMEDIATELY via POST /auth/change-password",
                default_pwd,
            )

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def create_user(self, email: str, password: str, role: str = "developer") -> User:
        """Create a new user. Raises ValueError if email already exists."""
        pwd_ctx = _get_pwd_context()
        hashed = pwd_ctx.hash(password)
        user_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                "INSERT INTO users (id, email, hashed_password, role, created_at) VALUES (?,?,?,?,?)",
                (user_id, email.lower().strip(), hashed, role, now),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Email already registered: {email}")
        logger.info("[UserStore] user created: email=%s role=%s", email, role)
        return User(id=user_id, email=email, hashed_password=hashed, role=role, created_at=now, last_login=None)

    def get_by_email(self, email: str) -> Optional[User]:
        """Return user by email, or None if not found."""
        row = self._conn.execute(
            "SELECT id, email, hashed_password, role, created_at, last_login FROM users WHERE email=?",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return None
        return User(id=row[0], email=row[1], hashed_password=row[2], role=row[3], created_at=row[4], last_login=row[5])

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Return user by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT id, email, hashed_password, role, created_at, last_login FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return User(id=row[0], email=row[1], hashed_password=row[2], role=row[3], created_at=row[4], last_login=row[5])

    def verify_password(self, email: str, password: str) -> Optional[User]:
        """Return User if credentials are valid, None otherwise."""
        user = self.get_by_email(email)
        if not user:
            # Constant-time dummy check to prevent user enumeration via timing
            _get_pwd_context().dummy_verify()
            return None
        pwd_ctx = _get_pwd_context()
        if not pwd_ctx.verify(password, user.hashed_password):
            return None
        # Update last_login
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE users SET last_login=? WHERE id=?", (now, user.id))
        self._conn.commit()
        return user

    def update_role(self, user_id: str, role: str) -> bool:
        """Update user role. Returns True if user found and updated."""
        if role not in ("admin", "developer", "viewer"):
            raise ValueError(f"Invalid role: {role}")
        result = self._conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        self._conn.commit()
        return result.rowcount > 0

    def list_users(self) -> list[dict]:
        """Return all users (admin use). Never includes hashed_password."""
        rows = self._conn.execute(
            "SELECT id, email, role, created_at, last_login FROM users ORDER BY created_at"
        ).fetchall()
        return [{"id": r[0], "email": r[1], "role": r[2], "created_at": r[3], "last_login": r[4]} for r in rows]

    def delete_user(self, user_id: str) -> bool:
        """Delete user. Also deletes their refresh tokens."""
        self._conn.execute("DELETE FROM refresh_tokens WHERE user_id=?", (user_id,))
        result = self._conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        self._conn.commit()
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Refresh token operations
    # ------------------------------------------------------------------

    def create_refresh_token(self, user_id: str, ttl_days: int = 7) -> str:
        """Generate and store a refresh token. Returns the plain token (stored as hash)."""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO refresh_tokens (token_hash, user_id, expires_at, invalidated, created_at) VALUES (?,?,?,0,?)",
            (token_hash, user_id, expires_at, now),
        )
        self._conn.commit()
        return token

    def validate_refresh_token(self, token: str) -> Optional[User]:
        """Validate a refresh token. Returns the User if valid, None otherwise."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = self._conn.execute(
            "SELECT user_id, expires_at, invalidated FROM refresh_tokens WHERE token_hash=?",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        user_id, expires_at, invalidated = row
        if invalidated:
            return None
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            return None
        return self.get_by_id(user_id)

    def invalidate_refresh_token(self, token: str) -> bool:
        """Invalidate a specific refresh token (logout)."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        result = self._conn.execute(
            "UPDATE refresh_tokens SET invalidated=1 WHERE token_hash=?", (token_hash,)
        )
        self._conn.commit()
        return result.rowcount > 0

    def invalidate_all_for_user(self, user_id: str) -> int:
        """Invalidate all refresh tokens for a user (logout everywhere)."""
        result = self._conn.execute(
            "UPDATE refresh_tokens SET invalidated=1 WHERE user_id=?", (user_id,)
        )
        self._conn.commit()
        return result.rowcount


# Singleton — shared process-wide
_store: UserStore | None = None


def get_user_store() -> UserStore:
    """Return the process-wide UserStore singleton."""
    global _store
    if _store is None:
        _store = UserStore()
    return _store

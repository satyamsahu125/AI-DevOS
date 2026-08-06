"""R8 — In-memory sliding-window rate limiter.

Pre-R10 implementation: stores counters in a process-level dict.
Post-R10 (Redis): replace the _store dict with Redis ZRANGEBYSCORE.

Limits enforced:
  - DEFAULT_LIMIT req/min per user (default 60)
  - PIPELINE_LIMIT pipeline starts/hour per user (default 5)
  - CHAT_LIMIT chat messages/hour per user (default 100)

When RATE_LIMIT_ENABLED=false (default), all requests pass through.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() in ("true", "1", "yes")
DEFAULT_LIMIT = int(os.getenv("RATE_LIMIT_DEFAULT", "60"))      # req/min
PIPELINE_LIMIT = int(os.getenv("RATE_LIMIT_PIPELINE", "5"))     # pipeline starts/hr
CHAT_LIMIT = int(os.getenv("RATE_LIMIT_CHAT", "100"))           # chat messages/hr

# _store: key → deque of timestamps (float seconds)
_store: dict[str, deque] = {}
_lock = threading.Lock()


def _check_limit(key: str, limit: int, window_seconds: int) -> None:
    """Sliding-window check. Raises HTTPException(429) if over limit.

    Parameters
    ----------
    key : str
        Unique identifier for this rate-limit bucket (e.g. "user:abc123:default").
    limit : int
        Maximum number of requests allowed in window_seconds.
    window_seconds : int
        Length of the sliding window in seconds.
    """
    if not RATE_LIMIT_ENABLED:
        return

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        if key not in _store:
            _store[key] = deque()
        dq = _store[key]
        # Evict entries outside the window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            # Retry-After: seconds until the oldest entry expires
            retry_after = int(dq[0] + window_seconds - now) + 1
            logger.warning("[rate_limit] 429: key=%s limit=%d window=%ds", key, limit, window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


def check_default(user_id: str) -> None:
    """60 requests/minute per user."""
    _check_limit(f"user:{user_id}:default", DEFAULT_LIMIT, 60)


def check_pipeline(user_id: str) -> None:
    """5 pipeline starts/hour per user."""
    _check_limit(f"user:{user_id}:pipeline", PIPELINE_LIMIT, 3600)


def check_chat(user_id: str) -> None:
    """100 chat messages/hour per user."""
    _check_limit(f"user:{user_id}:chat", CHAT_LIMIT, 3600)

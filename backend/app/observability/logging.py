"""logging.py — Structured logging configuration for AI DevOS.

Configures the standard logging module to emit either:
- JSON format (production): LOG_FORMAT=json in .env
- Colored text format (development): LOG_FORMAT=text (default)

JSON output includes project_id, stage, attempt as bound context fields when
set via the bind() context variable.

Usage:
    from app.observability.logging import configure_logging
    configure_logging()  # call once at startup, before any log statements

    # In agent/engine code — bind per-request context:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("stage started", extra={"project_id": project_id, "stage": stage})

Design:
    - Uses standard Python logging (not structlog) to remain lightweight
    - JSON formatter writes each log line as a single JSON object
    - Text formatter uses human-readable colored output for dev
    - LOG_LEVEL env var controls root logger level (default INFO)
    - Keeps dependency surface minimal — no structlog/loguru required
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


_LOG_FORMAT = os.getenv("LOG_FORMAT", "text").lower()
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON object.

    Standard fields: timestamp, level, logger, message.
    Extra context fields: project_id, stage, attempt (set via extra= parameter).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Inject bound context fields when present
        for field in ("project_id", "stage", "attempt", "request_id"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        # Include exception info when present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class _TextFormatter(logging.Formatter):
    """Human-readable colored formatter for development.

    Format: LEVEL:LOGGER:MESSAGE
    (standard Python format with level and logger name)
    """

    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._LEVEL_COLORS.get(record.levelname, "")
        reset = self._RESET
        # Inject context fields inline when present (only in text mode — JSON handles them structurally)
        ctx_parts = []
        for field in ("project_id", "stage", "attempt"):
            value = getattr(record, field, None)
            if value is not None:
                ctx_parts.append(f"{field}={value}")
        ctx = f" [{', '.join(ctx_parts)}]" if ctx_parts else ""

        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{color}{record.levelname}{reset}:{record.name}:{msg}{ctx}"


def configure_logging() -> None:
    """Configure the root logger based on LOG_FORMAT and LOG_LEVEL env vars.

    Safe to call multiple times — reconfigures the existing root handler if
    already set up. Called once at application startup in kernel.py.

    Silences overly verbose third-party loggers (uvicorn.access, httpx)
    to reduce noise in production.
    """
    level = _LEVEL_MAP.get(_LOG_LEVEL, logging.INFO)

    if _LOG_FORMAT == "json":
        formatter: logging.Formatter = _JSONFormatter()
    else:
        formatter = _TextFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace all existing handlers to avoid duplicate output
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "logging configured: format=%s level=%s", _LOG_FORMAT, _LOG_LEVEL
    )

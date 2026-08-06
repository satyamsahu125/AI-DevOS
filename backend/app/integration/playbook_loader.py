"""R6 — PlaybookLoader: loads and serves service integration playbooks.

Playbooks are JSON files in integration/playbooks/*.json. Each describes:
- Service metadata (name, keywords)
- Required environment variables
- Code snippets for Python and Node stacks
- Package dependencies

Design: loaded once at first use, cached in-process. No file watching —
adding a playbook requires a server restart (acceptable for now).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLAYBOOKS_DIR = Path(__file__).parent / "playbooks"

# Module-level cache: loaded once, reused for the process lifetime.
_cache: dict[str, dict[str, Any]] | None = None


def _load_all() -> dict[str, dict[str, Any]]:
    """Load all *.json playbooks from the playbooks directory into a service → dict map."""
    global _cache
    if _cache is not None:
        return _cache
    result: dict[str, dict[str, Any]] = {}
    if not _PLAYBOOKS_DIR.exists():
        logger.warning("[PlaybookLoader] playbooks directory not found: %s", _PLAYBOOKS_DIR)
        _cache = result
        return result
    for path in sorted(_PLAYBOOKS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            service = data.get("service") or path.stem
            result[service] = data
        except Exception as exc:
            logger.warning("[PlaybookLoader] failed to load %s: %s", path.name, exc)
    logger.info("[PlaybookLoader] loaded %d playbook(s): %s", len(result), list(result.keys()))
    _cache = result
    return result


def list_services() -> list[str]:
    """Return sorted list of available service names."""
    return sorted(_load_all().keys())


def get(service: str) -> dict[str, Any] | None:
    """Return the playbook for service, or None if not found."""
    return _load_all().get(service)


def detect_from_text(text: str) -> list[str]:
    """Detect which services are mentioned in text by keyword matching.

    Matches each playbook's 'keywords' list against the text (case-insensitive).
    Returns a sorted list of matched service names.

    Parameters
    ----------
    text : str
        Architecture document, requirements, or any descriptive text.

    Returns
    -------
    list[str]
        Service names whose keywords appear in the text.
    """
    text_lower = text.lower()
    detected: list[str] = []
    for service, playbook in _load_all().items():
        keywords: list[str] = playbook.get("keywords", [])
        if any(kw.lower() in text_lower for kw in keywords):
            detected.append(service)
    return sorted(detected)


def get_env_vars(services: list[str]) -> list[dict[str, Any]]:
    """Return all required env var specs for the given services (deduplicated by name).

    Parameters
    ----------
    services : list[str]
        List of service names to collect env vars for.

    Returns
    -------
    list[dict]
        Each dict has: name, description, required, service (source).
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for service in services:
        playbook = get(service)
        if not playbook:
            continue
        for ev in playbook.get("env_vars", []):
            name = ev.get("name", "")
            if name and name not in seen:
                seen.add(name)
                result.append({**ev, "service": service})
    return result

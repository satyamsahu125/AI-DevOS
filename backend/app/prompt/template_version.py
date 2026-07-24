from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TemplateVersion:
    """Represents a prompt-template version."""

    version: str = "1"
    status: str = "active"

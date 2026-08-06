"""Shared kernel container registry.

Eliminates the dual-container bug where api/dependencies.py built its own
Container() independently of AIKernel, resulting in two separate DI trees with
separate singletons, separate SQLite connections, and separate WorkflowManagers.

Usage:
  # In app startup (main.py lifespan):
  from .kernel.registry import set_container
  set_container(kernel.container)

  # In api/dependencies.py:
  from ..kernel.registry import get_container
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container

_container: "Container | None" = None


def set_container(c: "Container") -> None:  # called once from main.py lifespan
    global _container
    _container = c


def get_container_instance() -> "Container":
    if _container is None:
        # Fallback: build a fresh container so unit tests that never call
        # set_container() still work without importing main.py.
        from .container import Container
        return Container().build()
    return _container

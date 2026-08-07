from __future__ import annotations

from collections import OrderedDict
from typing import Any


class MemoryCache:
    """Caches the most recently used memory records."""

    def __init__(self, max_size: int = 50) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        value = self._cache.pop(key, None)
        if value is not None:
            self._cache[key] = value
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = value
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

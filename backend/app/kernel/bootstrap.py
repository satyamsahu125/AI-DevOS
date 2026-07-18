from __future__ import annotations

from .container import Container


class Bootstrap:
    def __init__(self, container: Container | None = None) -> None:
        self._container = container or Container()

    def initialize(self) -> Container:
        return self._container.build()

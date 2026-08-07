from abc import ABC, abstractmethod

from ..models.memory_entry import MemoryEntry


class MemoryInterface(ABC):
    @abstractmethod
    def store(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str) -> MemoryEntry | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

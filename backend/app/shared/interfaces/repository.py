from abc import ABC, abstractmethod

from ..models.project import Project


class Repository(ABC):
    @abstractmethod
    def save(self, model: Project) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self, id: str) -> Project:
        raise NotImplementedError

    @abstractmethod
    def update(self, model: Project) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, id: str) -> None:
        raise NotImplementedError

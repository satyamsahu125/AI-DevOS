from abc import ABC, abstractmethod


class SessionInterface(ABC):
    @abstractmethod
    def create(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def update(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def archive(self) -> None:
        raise NotImplementedError

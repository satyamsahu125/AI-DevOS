from .memory_repository import (
    MemoryAlreadyExistsException,
    MemoryNotFoundException,
    MemoryRepository,
    RepositoryDeleteException,
    RepositoryQueryException,
    RepositoryStorageException,
    RepositoryUpdateException,
    RepositoryValidationException,
)
from .repository_models import MemoryPage, MemoryRecord, MemorySearchResult
from .repository_query import RepositoryQuery
from .repository_filters import RepositoryFilter

__all__ = [
    "MemoryRepository",
    "RepositoryQuery",
    "RepositoryFilter",
    "MemoryRecord",
    "MemorySearchResult",
    "MemoryPage",
    "RepositoryValidationException",
    "MemoryNotFoundException",
    "MemoryAlreadyExistsException",
    "RepositoryStorageException",
    "RepositoryQueryException",
    "RepositoryUpdateException",
    "RepositoryDeleteException",
]


def __getattr__(name: str):
    if name == "MemoryContext":
        from .memory_context import MemoryContext
        return MemoryContext
    if name == "MemoryContextBuilder":
        from .memory_context_builder import MemoryContextBuilder
        return MemoryContextBuilder
    if name == "MemoryManager":
        from .memory_manager import MemoryManager
        return MemoryManager
    raise AttributeError(name)

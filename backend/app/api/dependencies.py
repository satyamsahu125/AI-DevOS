from __future__ import annotations

from fastapi import Depends

from ..artifact.manager import ArtifactManager
from ..kernel.container import Container
from ..llm.manager import LLMManager
from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.learning_loop import LearningLoop
from ..memory.manager import MemoryManager
from ..memory.project_event_log import ProjectEventLog
from ..project.manager import ProjectManager
from ..workflow.manager import WorkflowManager
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager


_container = Container().build()


def get_container() -> Container:
    return _container


def get_project_manager(container: Container = Depends(get_container)) -> ProjectManager:
    return container.project_manager


def get_workflow_manager(container: Container = Depends(get_container)) -> WorkflowManager:
    return container.workflow_manager


def get_workspace_manager(container: Container = Depends(get_container)) -> WorkspaceManager:
    return container.workspace_manager


def get_artifact_manager(container: Container = Depends(get_container)) -> ArtifactManager:
    return container.artifact_manager


def get_llm_manager(container: Container = Depends(get_container)) -> LLMManager:
    return container.llm_manager


def get_memory_manager(container: Container = Depends(get_container)) -> MemoryManager:
    return container.memory_manager


def get_learning_loop(container: Container = Depends(get_container)) -> LearningLoop:
    return container.learning_loop


def get_knowledge_memory(container: Container = Depends(get_container)) -> KnowledgeMemory:
    return container.knowledge_memory


def get_project_file_manager(container: Container = Depends(get_container)) -> ProjectFileManager:
    return container.project_file_manager


def get_event_log(container: Container = Depends(get_container)) -> ProjectEventLog:
    return container.event_log

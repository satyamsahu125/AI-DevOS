from __future__ import annotations

from fastapi import Depends

from ..kernel.container import Container
from ..project.manager import ProjectManager
from ..workflow.manager import WorkflowManager


_container = Container().build()


def get_container() -> Container:
    return _container


def get_project_manager(container: Container = Depends(get_container)) -> ProjectManager:
    return container.project_manager


def get_workflow_manager(container: Container = Depends(get_container)) -> WorkflowManager:
    return container.workflow_manager

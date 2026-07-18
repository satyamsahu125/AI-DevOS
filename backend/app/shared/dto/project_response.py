from dataclasses import dataclass

from ..models.project import Project


@dataclass(slots=True)
class ProjectResponse:
    project: Project
    success: bool
    message: str

    @property
    def project_id(self) -> str:
        return self.project.project_id

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def description(self) -> str:
        return self.project.description

    @property
    def workspace_path(self) -> str:
        return self.project.workspace_path

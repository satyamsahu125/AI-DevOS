from dataclasses import dataclass


@dataclass(slots=True)
class ProjectRequest:
    name: str
    description: str

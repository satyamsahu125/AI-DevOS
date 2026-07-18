from enum import Enum


class Stage(str, Enum):
    ProductOwner = "ProductOwner"
    Reviewer = "Reviewer"
    Architect = "Architect"
    Planner = "Planner"
    BackendDeveloper = "BackendDeveloper"
    FrontendDeveloper = "FrontendDeveloper"

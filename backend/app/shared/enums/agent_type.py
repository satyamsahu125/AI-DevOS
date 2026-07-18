from enum import Enum


class AgentType(str, Enum):
    ProductOwner = "ProductOwner"
    Reviewer = "Reviewer"
    Architect = "Architect"
    Planner = "Planner"
    BackendDeveloper = "BackendDeveloper"
    FrontendDeveloper = "FrontendDeveloper"

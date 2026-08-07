from enum import Enum


class AgentType(str, Enum):
    ProductOwner = "ProductOwner"
    Reviewer = "Reviewer"
    Architect = "Architect"
    Planner = "Planner"
    BackendDeveloper = "BackendDeveloper"
    FrontendDeveloper = "FrontendDeveloper"
    QA = "QA"
    DevOps = "DevOps"
    StrategicReview = "StrategicReview"
    Designer = "Designer"
    Security = "Security"
    Document = "Document"
    Retro = "Retro"

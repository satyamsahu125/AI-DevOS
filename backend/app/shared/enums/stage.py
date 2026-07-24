from enum import Enum


class Stage(str, Enum):
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
    FileStructurePlanner = "FileStructurePlanner"
    Document = "Document"
    Retro = "Retro"

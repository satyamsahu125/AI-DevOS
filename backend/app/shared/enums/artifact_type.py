from enum import Enum


class ArtifactType(str, Enum):
    Requirements = "Requirements"
    Architecture = "Architecture"
    ImplementationPlan = "ImplementationPlan"
    BackendCode = "BackendCode"
    FrontendCode = "FrontendCode"

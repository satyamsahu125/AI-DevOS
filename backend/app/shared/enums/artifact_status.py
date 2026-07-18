from enum import Enum


class ArtifactStatus(str, Enum):
    Draft = "Draft"
    Generated = "Generated"
    Stored = "Stored"
    Approved = "Approved"
    VersionLocked = "VersionLocked"

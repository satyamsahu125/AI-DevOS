from enum import Enum


class MemoryType(str, Enum):
    Runtime = "Runtime"
    Project = "Project"
    Session = "Session"
    Design = "Design"

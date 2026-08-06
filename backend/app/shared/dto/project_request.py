from dataclasses import dataclass, field


@dataclass(slots=True)
class ProjectRequest:
    name: str
    description: str
    mode: str = "full"  # R9: "full" (default) or "quick" (prototype — skips Security/Doc/Retro/HumanGates)

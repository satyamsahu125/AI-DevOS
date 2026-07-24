from __future__ import annotations

from ..shared.schemas.architecture_schema import ArchitectureArtifact


def summarize_architecture(architecture: ArchitectureArtifact | None) -> str:
    """Compact, LLM-friendly text summary of an ArchitectureArtifact.

    Shared by WriteFilePlanAction and WriteProjectFilesAction, both of which
    need to hand a focused slice of the architecture to a per-file LLM call
    rather than the whole structured object.
    """
    if architecture is None:
        return "(no architecture available)"
    lines: list[str] = []
    if architecture.approach:
        lines.append(f"Approach: {architecture.approach}")
    if architecture.tech_stack:
        lines.append("Tech stack: " + ", ".join(f"{layer}={tech}" for layer, tech in architecture.tech_stack.items()))
    if architecture.modules:
        lines.append("Modules: " + "; ".join(f"{m.name} ({m.purpose})" for m in architecture.modules))
    if architecture.api_design:
        lines.append("API endpoints: " + "; ".join(f"{e.method} {e.path}" for e in architecture.api_design))
    if architecture.data_models:
        lines.append("Data models: " + "; ".join(m.name for m in architecture.data_models))
    return "\n".join(lines) if lines else "(architecture has no details)"

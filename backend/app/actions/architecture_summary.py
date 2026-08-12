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
    # project_type is listed first so every downstream stage reading this summary
    # immediately knows what kind of project it is building.
    project_type = architecture.project_type or "web_fullstack"
    lines.append(f"Project type: {project_type}")
    if architecture.approach:
        lines.append(f"Approach: {architecture.approach}")
    if architecture.tech_stack:
        lines.append("Tech stack: " + ", ".join(f"{layer}={tech}" for layer, tech in architecture.tech_stack.items()))
    if architecture.modules:
        # Include file paths so FilePlan LLM can see what the Architect intended
        module_parts = []
        for m in architecture.modules:
            part = f"{m.name} ({m.purpose})"
            if m.files:
                part += " [files: " + ", ".join(m.files[:3]) + "]"
            module_parts.append(part)
        lines.append("Modules: " + "; ".join(module_parts))
    api_list = architecture.api_endpoints or architecture.api_design
    if api_list:
        lines.append("API endpoints: " + "; ".join(f"{e.method} {e.path}" for e in api_list))
    if architecture.data_models:
        lines.append("Data models: " + "; ".join(m.name for m in architecture.data_models))
    return "\n".join(lines) if lines else "(architecture has no details)"

from __future__ import annotations

from dataclasses import dataclass

_STACK_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "node",
    ".jsx": "node",
    ".ts": "node",
    ".tsx": "node",
    ".mjs": "node",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
}

_RUN_STEPS: dict[str, list[str]] = {
    "python": [
        "python -m venv .venv",
        ".venv\\Scripts\\activate  # (Windows) or: source .venv/bin/activate  # (macOS/Linux)",
        "pip install -r requirements.txt   # installs dependencies from requirements.txt",
        "python main.py   # or python app.py",
    ],
    "node": [
        "npm install",
        "npm start   # (runs dev server or node entrypoint)",
    ],
    "go": ["go mod init module", "go run ."],
    "ruby": ["bundle install", "ruby app.rb"],
    "java": ["mvn compile && mvn exec:java"],
}

_MANIFEST_HINTS = {
    "package.json": "node",
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "go.mod": "go",
    "Gemfile": "ruby",
    "pom.xml": "java",
}


@dataclass(slots=True)
class AreaSummary:
    area: str
    files: list[str]
    detected_stack: str | None
    has_manifest: bool


def _detect_stack(files: list[str]) -> str | None:
    """Return the most common language among files' extensions, or None if there are no files."""
    counts: dict[str, int] = {}
    for file_path in files:
        for ext, stack in _STACK_BY_EXTENSION.items():
            if file_path.endswith(ext):
                counts[stack] = counts.get(stack, 0) + 1
                break
    if not counts:
        return None
    return max(counts, key=lambda stack: counts[stack])


def _has_manifest(files: list[str]) -> bool:
    names = {file_path.rsplit("/", 1)[-1] for file_path in files}
    return any(manifest in names for manifest in _MANIFEST_HINTS)


def summarize_area(area: str, files: list[str]) -> AreaSummary:
    return AreaSummary(area=area, files=sorted(files), detected_stack=_detect_stack(files), has_manifest=_has_manifest(files))


def build_run_instructions(project_name: str, description: str, backend_files: list[str], frontend_files: list[str]) -> str:
    """Build a deterministic README covering what was generated and how to run it."""
    backend = summarize_area("backend", backend_files)
    frontend = summarize_area("frontend", frontend_files)

    lines = [f"# {project_name}", "", description.strip() or "_No description provided._", ""]

    for summary in (backend, frontend):
        if not summary.files:
            continue
        lines.append(f"## {summary.area.capitalize()}")
        lines.append("")
        lines.append(f"**Detected stack:** {summary.detected_stack or 'unknown'}")
        if not summary.has_manifest:
            lines.append(
                "> Note: Package manifest automatically created on export."
            )
        lines.append("")
        lines.append("**Files generated:**")
        for file_path in summary.files:
            lines.append(f"- `{summary.area}/{file_path}`")
        lines.append("")
        lines.append("**To run:**")
        lines.append("```bash")
        lines.append(f"cd {summary.area}")
        for step in _RUN_STEPS.get(summary.detected_stack or "", ["npm install && npm start"]):
            lines.append(step)
        lines.append("```")
        lines.append("")

    if not backend.files and not frontend.files:
        lines.append("_No files have been generated yet -- run the Backend/Frontend Developer stages first._")

    return "\n".join(lines)

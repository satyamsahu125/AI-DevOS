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
        "pip install -r requirements.txt   # if this file isn't present yet, install the imports each file needs",
        "python <entry point, e.g. main.py or app.py>",
    ],
    "node": [
        "npm install   # if package.json isn't present yet, run `npm init -y` first and add the packages each file imports",
        "npm start   # or: node <entry point, e.g. index.js or server.js>",
    ],
    "go": ["go mod init <module-name>   # if go.mod isn't present yet", "go run ."],
    "ruby": ["bundle install   # if a Gemfile isn't present yet", "ruby <entry point>"],
    "java": ["# Set up a build tool (Maven/Gradle) if none was generated, then build and run the main class"],
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
    """Build a best-effort, deterministic (non-LLM) README covering what was generated and how to run it.

    This is intentionally not another LLM call: the local model is unreliable enough on code
    generation itself (see file_plan_builder.py's leading-slash issue) that adding a second
    generative step just to describe how to run the first one's output would be one more thing
    that can silently go wrong. Everything here is derived directly from the files actually
    written to disk, so it's always consistent with what's really there -- even if that means
    being upfront that a dependency manifest is missing, rather than inventing one.
    """
    backend = summarize_area("backend", backend_files)
    frontend = summarize_area("frontend", frontend_files)

    lines = [f"# {project_name}", "", description.strip() or "_No description provided._", ""]

    for summary in (backend, frontend):
        if not summary.files:
            continue
        lines.append(f"## {summary.area.capitalize()}")
        lines.append("")
        lines.append(f"**Detected stack:** {summary.detected_stack or 'unknown (no recognized source file extensions)'}")
        if not summary.has_manifest:
            lines.append(
                "> No dependency manifest (package.json / requirements.txt / etc.) was generated for this area -- "
                "you'll likely need to create one and add whatever each file imports before it will run."
            )
        lines.append("")
        lines.append("**Files generated:**")
        for file_path in summary.files:
            lines.append(f"- `{summary.area}/{file_path}`")
        lines.append("")
        lines.append("**To run:**")
        lines.append("```")
        lines.append(f"cd project/{summary.area}")
        for step in _RUN_STEPS.get(summary.detected_stack or "", ["# Stack not recognized -- inspect the generated files to determine how to run them."]):
            lines.append(step)
        lines.append("```")
        lines.append("")

    if not backend.files and not frontend.files:
        lines.append("_No files have been generated yet -- run the Backend/Frontend Developer stages first._")

    return "\n".join(lines)

from __future__ import annotations

import re
import sys

_NODE_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_NODE_IMPORT = re.compile(r"""^\s*import\s+(?:[\w*${}\s,]+\s+from\s+)?['"]([^'"]+)['"]""", re.MULTILINE)
_PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
_PY_FROM_IMPORT = re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE)

_ENTRY_CANDIDATES = ("index.js", "server.js", "app.js", "main.js")


def _node_package_name(module_path: str) -> str | None:
    """Return the installable npm package name for an import path, or None for relative/local imports."""
    if module_path.startswith(".") or module_path.startswith("/"):
        return None
    parts = module_path.split("/")
    if module_path.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def detect_node_dependencies(file_contents: list[str]) -> list[str]:
    """Scan file contents for require()/import statements and return the unique external npm
    package names referenced (relative imports like "./foo" are never treated as packages)."""
    names: set[str] = set()
    for content in file_contents:
        for match in _NODE_REQUIRE.finditer(content):
            name = _node_package_name(match.group(1))
            if name:
                names.add(name)
        for match in _NODE_IMPORT.finditer(content):
            name = _node_package_name(match.group(1))
            if name:
                names.add(name)
    return sorted(names)


def detect_python_dependencies(file_contents: list[str]) -> list[str]:
    """Scan file contents for import/from-import statements and return the unique external
    (non-stdlib, non-relative) top-level package names referenced."""
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    names: set[str] = set()
    for content in file_contents:
        for pattern in (_PY_IMPORT, _PY_FROM_IMPORT):
            for match in pattern.finditer(content):
                top_level = match.group(1).split(".")[0]
                if top_level and top_level not in stdlib and not top_level.startswith("_"):
                    names.add(top_level)
    return sorted(names)


def build_package_json(project_name: str, dependencies: list[str], written_paths: list[str]) -> str:
    """Build a minimal package.json listing dependencies (as "*", since exact versions aren't
    knowable from source alone) and a best-guess start script from whatever entry file exists."""
    import json

    entry = next((path for path in written_paths if path in _ENTRY_CANDIDATES), None) or next(
        (path for path in written_paths if path.endswith(".js") and "/" not in path), None
    ) or (written_paths[0] if written_paths else "index.js")

    safe_name = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in project_name.lower()) or "generated-project"
    payload = {
        "name": safe_name,
        "version": "0.1.0",
        "private": True,
        "scripts": {"start": f"node {entry}"},
        "dependencies": {name: "*" for name in dependencies},
    }
    return json.dumps(payload, indent=2) + "\n"


def build_requirements_txt(dependencies: list[str]) -> str:
    """Build a requirements.txt with one unpinned package per line (versions aren't knowable
    from source alone -- this is a starting point, not a locked/reproducible manifest)."""
    return "\n".join(dependencies) + ("\n" if dependencies else "")

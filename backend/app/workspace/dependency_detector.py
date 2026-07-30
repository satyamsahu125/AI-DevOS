from __future__ import annotations

import logging
import re
import sys

logger = logging.getLogger(__name__)

PYTHON_VERSION_MAP = {
    "fastapi":              "fastapi>=0.115.0,<1.0.0",
    "pydantic":             "pydantic>=2.0.0,<3.0.0",
    "pydantic-settings":    "pydantic-settings>=2.0.0,<3.0.0",
    "sqlalchemy":           "SQLAlchemy>=2.0.0,<3.0.0",
    "alembic":              "alembic>=1.13.0,<2.0.0",
    "uvicorn":              "uvicorn[standard]>=0.30.0,<1.0.0",
    "httpx":                "httpx>=0.27.0,<1.0.0",
    "python-dotenv":        "python-dotenv>=1.0.0,<2.0.0",
    "bcrypt":               "bcrypt>=4.0.0,<5.0.0",
    "python-jose":          "python-jose[cryptography]>=3.3.0,<4.0.0",
    "passlib":              "passlib[bcrypt]>=1.7.0,<2.0.0",
    "pytest":               "pytest>=8.0.0",
    "pytest-asyncio":       "pytest-asyncio>=0.23.0",
    "pytest-cov":           "pytest-cov>=4.0.0",
    "redis":                "redis>=5.0.0,<6.0.0",
    "celery":               "celery>=5.3.0,<6.0.0",
    "pillow":               "Pillow>=10.0.0,<11.0.0",
    "requests":             "requests>=2.31.0,<3.0.0",
    "aiohttp":              "aiohttp>=3.9.0,<4.0.0",
    "psycopg2":             "psycopg2-binary>=2.9.0,<3.0.0",
    "pymongo":              "pymongo>=4.6.0,<5.0.0",
    "boto3":                "boto3>=1.34.0,<2.0.0",
    "stripe":               "stripe>=8.0.0,<9.0.0",
    "sendgrid":             "sendgrid>=6.11.0,<7.0.0",
    # Async DB drivers
    "asyncpg":              "asyncpg>=0.29.0,<1.0.0",
    "aiosqlite":            "aiosqlite>=0.20.0,<1.0.0",
    "motor":                "motor>=3.4.0,<4.0.0",
    # FastAPI / Starlette extras
    "python-multipart":     "python-multipart>=0.0.9,<1.0.0",
    "email-validator":      "email-validator>=2.1.0,<3.0.0",
    "starlette":            "starlette>=0.40.0,<1.0.0",
    "gunicorn":             "gunicorn>=22.0.0,<23.0.0",
    # ORM / data
    "sqlmodel":             "sqlmodel>=0.0.19,<1.0.0",
    "tortoise-orm":         "tortoise-orm>=0.21.0,<1.0.0",
    # HTTP / networking
    "websockets":           "websockets>=12.0,<13.0",
    "python-socketio":      "python-socketio>=5.11.0,<6.0.0",
    "tenacity":             "tenacity>=8.3.0,<9.0.0",
    # Auth / crypto
    "cryptography":         "cryptography>=42.0.0,<43.0.0",
    "pyjwt":                "PyJWT>=2.8.0,<3.0.0",
    "authlib":              "Authlib>=1.3.0,<2.0.0",
    # AI / LLM clients
    "openai":               "openai>=1.35.0,<2.0.0",
    "anthropic":            "anthropic>=0.31.0,<1.0.0",
    "google-generativeai":  "google-generativeai>=0.7.0,<1.0.0",
    # Data science
    "pandas":               "pandas>=2.2.0,<3.0.0",
    "numpy":                "numpy>=1.26.0,<2.0.0",
    "scikit-learn":         "scikit-learn>=1.5.0,<2.0.0",
    # Templating / utilities
    "jinja2":               "Jinja2>=3.1.0,<4.0.0",
    "python-slugify":       "python-slugify>=8.0.0,<9.0.0",
    "arrow":                "arrow>=1.3.0,<2.0.0",
    "humanize":             "humanize>=4.9.0,<5.0.0",
    "rich":                 "rich>=13.7.0,<14.0.0",
    "loguru":               "loguru>=0.7.0,<1.0.0",
    "structlog":            "structlog>=24.1.0,<25.0.0",
    # Testing extras
    "pytest-mock":          "pytest-mock>=3.14.0,<4.0.0",
    "freezegun":            "freezegun>=1.5.0,<2.0.0",
    "factory-boy":          "factory-boy>=3.3.0,<4.0.0",
    "hypothesis":           "hypothesis>=6.104.0",
    # Dev tools (often in requirements-dev.txt)
    "black":                "black>=24.4.0",
    "ruff":                 "ruff>=0.5.0",
    "mypy":                 "mypy>=1.10.0",
}

NPM_VERSION_MAP = {
    "react":                   "^18.3.0",
    "react-dom":               "^18.3.0",
    "next":                    "^14.2.0",
    "vite":                    "^5.3.0",
    "@vitejs/plugin-react":    "^4.3.0",
    "typescript":              "^5.4.0",
    "tailwindcss":             "^3.4.0",
    "framer-motion":           "^11.0.0",
    "lucide-react":            "^0.383.0",
    "axios":                   "^1.7.0",
    "react-router-dom":        "^6.24.0",
    "zustand":                 "^4.5.0",
    "react-query":             "^5.0.0",
    "@tanstack/react-query":   "^5.51.0",
    "zod":                     "^3.23.0",
    "react-hook-form":         "^7.52.0",
    "@radix-ui/react-dialog":  "^1.1.0",
    "@radix-ui/react-tooltip": "^1.1.0",
    "class-variance-authority":"^0.7.0",
    "clsx":                    "^2.1.0",
    "tailwind-merge":          "^2.4.0",
    "sonner":                  "^1.5.0",
    "express":                 "^4.19.0",
    "cors":                    "^2.8.5",
    "dotenv":                  "^16.4.0",
    "mongoose":                "^8.5.0",
    "prisma":                  "^5.16.0",
    "jsonwebtoken":            "^9.0.0",
    "bcryptjs":                "^2.4.3",
    "stripe":                  "^16.2.0",
    "socket.io":               "^4.7.0",
    "jest":                    "^29.7.0",
    "@testing-library/react":  "^16.0.0",
    # TypeScript type packages
    "@types/react":            "^18.3.0",
    "@types/react-dom":        "^18.3.0",
    "@types/node":             "^20.14.0",
    "@types/express":          "^4.17.0",
    "@types/cors":             "^2.8.0",
    "@types/lodash":           "^4.17.0",
    "@types/uuid":             "^9.0.0",
    # Testing
    "vitest":                  "^1.6.0",
    "@vitest/ui":              "^1.6.0",
    "@testing-library/jest-dom":   "^6.4.0",
    "@testing-library/user-event": "^14.5.0",
    "msw":                     "^2.3.0",
    "playwright":              "^1.45.0",
    "@playwright/test":        "^1.45.0",
    # Data fetching / state
    "swr":                     "^2.2.0",
    "jotai":                   "^2.9.0",
    "@reduxjs/toolkit":        "^2.3.0",
    "react-redux":             "^9.1.0",
    "immer":                   "^10.1.0",
    # UI components / icons
    "@headlessui/react":       "^2.1.0",
    "@heroicons/react":        "^2.1.0",
    "react-icons":             "^5.2.0",
    "@radix-ui/react-select":  "^2.1.0",
    "@radix-ui/react-dropdown-menu": "^2.1.0",
    "@radix-ui/react-popover": "^1.1.0",
    "@radix-ui/react-tabs":    "^1.1.0",
    "@radix-ui/react-switch":  "^1.1.0",
    "@radix-ui/react-checkbox": "^1.1.0",
    "@radix-ui/react-slider":  "^1.2.0",
    # Tables / data display
    "@tanstack/react-table":   "^8.19.0",
    "recharts":                "^2.12.0",
    # Date / utilities
    "date-fns":                "^3.6.0",
    "dayjs":                   "^1.11.0",
    "lodash":                  "^4.17.0",
    "lodash-es":               "^4.17.0",
    "uuid":                    "^10.0.0",
    # Forms
    "@hookform/resolvers":     "^3.9.0",
    # Realtime
    "socket.io-client":        "^4.7.0",
    # CSS tooling
    "postcss":                 "^8.4.0",
    "autoprefixer":            "^10.4.0",
    "sass":                    "^1.77.0",
    # Animation
    "react-spring":            "^9.7.0",
    # Misc
    "react-dropzone":          "^14.2.0",
    "react-helmet-async":      "^2.0.0",
    "react-hot-toast":         "^2.4.0",
    "next-auth":               "^4.24.0",
    "@supabase/supabase-js":   "^2.45.0",
    "graphql":                 "^16.9.0",
    "@apollo/client":          "^3.11.0",
}

_NODE_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_NODE_IMPORT = re.compile(r"""^\s*import\s+(?:[\w*${}\s,]+\s+from\s+)?['"]([^'"]+)['"]""", re.MULTILINE)
_PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE)
_PY_FROM_IMPORT = re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE)

_ENTRY_CANDIDATES = ("index.js", "server.js", "app.js", "main.js", "src/index.js", "src/main.js")


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


def _clean_path(path: str) -> str:
    """Strip leading 'backend/' or 'frontend/' prefixes if present."""
    p = path.replace("\\", "/")
    if p.lower().startswith("backend/"):
        return p[8:]
    if p.lower().startswith("frontend/"):
        return p[9:]
    return p


def build_package_json(project_name: str, dependencies: list[str], written_paths: list[str]) -> str:
    """Build a valid, robust package.json listing pinned dependencies and clean, executable npm scripts."""
    import json

    def pin(pkg: str) -> str:
        version = NPM_VERSION_MAP.get(pkg.lower())
        if not version:
            logger.warning(
                "Unknown npm package '%s' — using 'latest'. "
                "Add to NPM_VERSION_MAP.", pkg
            )
            return "latest"
        return version

    cleaned_paths = [_clean_path(p) for p in written_paths if p]
    is_frontend = any(
        p.endswith((".jsx", ".tsx", ".html")) or "react" in p.lower() or "src/components" in p.lower()
        for p in cleaned_paths
    )

    safe_name = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in project_name.lower()) or "generated-project"

    if is_frontend:
        # React/Vite/Web Frontend package.json
        dept_dict = {name: pin(name) for name in dependencies}
        if "react" not in dept_dict:
            dept_dict["react"] = NPM_VERSION_MAP.get("react", "^18.3.0")
        if "react-dom" not in dept_dict:
            dept_dict["react-dom"] = NPM_VERSION_MAP.get("react-dom", "^18.3.0")

        payload = {
            "name": safe_name,
            "version": "0.1.0",
            "private": True,
            "type": "module",
            "scripts": {
                "dev": "vite",
                "start": "vite",
                "build": "vite build",
                "preview": "vite preview",
            },
            "dependencies": dept_dict,
            "devDependencies": {
                "@vitejs/plugin-react": NPM_VERSION_MAP.get("@vitejs/plugin-react", "^4.3.0"),
                "vite": NPM_VERSION_MAP.get("vite", "^5.3.0"),
            },
        }
    else:
        # Node.js Backend package.json
        entry = (
            next((path for path in cleaned_paths if path in _ENTRY_CANDIDATES), None)
            or next((path for path in cleaned_paths if path.endswith(".js") and "/" not in path), None)
            or next((path for path in cleaned_paths if path.endswith(".js")), None)
            or "index.js"
        )

        payload = {
            "name": safe_name,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "start": f"node {entry}",
                "dev": f"node {entry}",
            },
            "dependencies": {name: pin(name) for name in dependencies},
        }

    return json.dumps(payload, indent=2) + "\n"


def build_requirements_txt(dependencies: list[str]) -> str:
    """Build a requirements.txt with pinned versions."""
    lines = []
    for pkg in dependencies:
        pkg_lower = pkg.lower().replace("-", "_").replace(".", "_")
        pinned = (
            PYTHON_VERSION_MAP.get(pkg.lower()) or
            PYTHON_VERSION_MAP.get(pkg_lower)
        )
        if pinned:
            lines.append(pinned)
        else:
            # Emit the package unpinned rather than blocking generation.
            # The warning below tells developers to add it to PYTHON_VERSION_MAP.
            lines.append(f"{pkg}  # unpinned — add to PYTHON_VERSION_MAP")
            logger.warning(
                "Unknown Python package '%s' — not pinned. "
                "Add to PYTHON_VERSION_MAP in dependency_detector.py.", pkg
            )
    return "\n".join(sorted(lines)) + ("\n" if lines else "")

"""APIContractExtractor — scans written backend files for route definitions.

After BackendDeveloper writes files, this extractor scans them for HTTP route
declarations and produces an APIContractArtifact.  FrontendDeveloper reads this
artifact so it calls the exact paths/methods the backend actually exposes —
not paths it guesses from the Architecture spec.

Supported patterns:
  FastAPI / APIRouter  →  @router.get("/path"), @app.post("/path"), etc.
  Express (JS/TS)      →  router.get('/path', ...), app.post('/path', ...)
  Flask                →  @app.route('/path', methods=['GET', 'POST'])
  Django URLs          →  path('url/', view)  — basic detection only
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Route detection regexes ───────────────────────────────────────────────────

# FastAPI / Starlette: @router.get("/users"), @app.delete("/items/{id}")
_FASTAPI_RE = re.compile(
    r'@\w+\.(get|post|put|patch|delete|head|options|websocket)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Express: router.get('/users', handler) or app.post('/items/:id', ...)
_EXPRESS_RE = re.compile(
    r'\b(?:router|app)\.(get|post|put|patch|delete|all)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Flask: @app.route('/path', methods=['GET', 'POST'])
_FLASK_ROUTE_RE = re.compile(
    r'@\w+\.route\s*\(\s*["\']([^"\']+)["\'][^)]*methods\s*=\s*\[([^\]]+)\]',
    re.IGNORECASE,
)
_FLASK_ROUTE_SIMPLE_RE = re.compile(
    r'@\w+\.route\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# Flask shorthand: @app.get, @app.post
_FLASK_SHORT_RE = re.compile(
    r'@\w+\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Django: path('endpoint/', SomeView.as_view())
_DJANGO_PATH_RE = re.compile(
    r'\bpath\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


@dataclass
class RouteEntry:
    method: str       # uppercase HTTP method, e.g. "GET"
    path: str         # URL path, e.g. "/api/users/{id}"
    source_file: str  # relative path of the file that declares this route


@dataclass
class APIContractArtifact:
    """All HTTP routes discovered across backend-written files."""
    routes: list[RouteEntry] = field(default_factory=list)
    base_url: str = ""  # populated by caller if known (e.g. "/api/v1")

    def as_prompt_section(self) -> str:
        """Return a compact, human-readable section for injection into prompts."""
        if not self.routes:
            return ""
        lines = ["## Backend API Contract (actual endpoints — use these exact paths)"]
        for r in self.routes:
            lines.append(f"  {r.method.upper():7s} {r.path}")
        lines.append(
            "\nAlways call these exact paths and methods. "
            "Do NOT invent new endpoints or guess paths."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "routes": [
                {"method": r.method, "path": r.path, "source_file": r.source_file}
                for r in self.routes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "APIContractArtifact":
        routes = [
            RouteEntry(
                method=r.get("method", "GET"),
                path=r.get("path", "/"),
                source_file=r.get("source_file", ""),
            )
            for r in data.get("routes", [])
        ]
        return cls(routes=routes, base_url=data.get("base_url", ""))


class APIContractExtractor:
    """Scans a list of (path, content) pairs and extracts all route declarations."""

    def extract(self, files: list[tuple[str, str]]) -> APIContractArtifact:
        """Scan files and return an APIContractArtifact.

        Parameters
        ----------
        files:
            List of (relative_path, file_content) tuples from the written backend files.
        """
        routes: list[RouteEntry] = []
        seen: set[tuple[str, str]] = set()

        for rel_path, content in files:
            ext = Path(rel_path).suffix.lower()
            if ext in (".py", ".pyw"):
                extracted = self._extract_python(rel_path, content)
            elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
                extracted = self._extract_js(rel_path, content)
            else:
                continue

            for entry in extracted:
                key = (entry.method.upper(), entry.path)
                if key not in seen:
                    seen.add(key)
                    routes.append(RouteEntry(
                        method=entry.method.upper(),
                        path=entry.path,
                        source_file=rel_path,
                    ))

        logger.info(
            "APIContractExtractor: found %d unique routes across %d files",
            len(routes), len(files),
        )
        return APIContractArtifact(routes=routes)

    # ── Python route extractors ───────────────────────────────────────────────

    @staticmethod
    def _extract_python(path: str, content: str) -> list[RouteEntry]:
        entries: list[RouteEntry] = []

        # FastAPI / Starlette
        for m in _FASTAPI_RE.finditer(content):
            entries.append(RouteEntry(method=m.group(1).upper(), path=m.group(2), source_file=path))

        # Flask @app.route with explicit methods list
        for m in _FLASK_ROUTE_RE.finditer(content):
            route_path = m.group(1)
            methods_raw = m.group(2)
            methods = [x.strip().strip("'\"") for x in methods_raw.split(",") if x.strip()]
            for method in methods:
                entries.append(RouteEntry(method=method.upper(), path=route_path, source_file=path))

        # Flask @app.route without methods → assume GET
        for m in _FLASK_ROUTE_SIMPLE_RE.finditer(content):
            route_path = m.group(1)
            # Skip if already captured by the methods-list pattern
            if not any(e.path == route_path for e in entries):
                entries.append(RouteEntry(method="GET", path=route_path, source_file=path))

        # Flask shorthand @app.get / @app.post
        for m in _FLASK_SHORT_RE.finditer(content):
            entries.append(RouteEntry(method=m.group(1).upper(), path=m.group(2), source_file=path))

        return entries

    # ── JavaScript / TypeScript route extractors ──────────────────────────────

    @staticmethod
    def _extract_js(path: str, content: str) -> list[RouteEntry]:
        entries: list[RouteEntry] = []
        for m in _EXPRESS_RE.finditer(content):
            entries.append(RouteEntry(method=m.group(1).upper(), path=m.group(2), source_file=path))
        return entries


# ── Persistence helpers ───────────────────────────────────────────────────────

def save_api_contract(workspace_path: Path, project_id: str, contract: APIContractArtifact) -> None:
    """Persist the API contract as a JSON artifact alongside the sprint plan."""
    artifacts_dir = workspace_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "api_contract.json"
    out.write_text(json.dumps(contract.to_dict(), indent=2), encoding="utf-8")
    logger.info("APIContractExtractor: saved %d routes to %s", len(contract.routes), out)


def load_api_contract(workspace_path: Path, project_id: str) -> APIContractArtifact | None:
    """Load a previously saved API contract, or return None if not found."""
    path = workspace_path / "artifacts" / "api_contract.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        contract = APIContractArtifact.from_dict(data)
        logger.debug("APIContractExtractor: loaded %d routes from %s", len(contract.routes), path)
        return contract
    except Exception as exc:
        logger.warning("APIContractExtractor: failed to load %s: %s", path, exc)
        return None

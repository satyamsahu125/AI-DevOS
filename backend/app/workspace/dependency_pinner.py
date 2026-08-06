"""dependency_pinner.py — Pin dependencies to exact stable versions.

R2: After BackendDeveloper generates requirements.txt (or package.json),
resolve each package against the PyPI/npm registry and rewrite the file
with pinned versions (e.g. fastapi==0.111.0 instead of fastapi>=0.100).

Design:
- Session-level cache: each package is resolved once per Python process
- Best-effort: if resolution fails, the original line is kept unchanged
- Skips lines that already have == (already pinned)
- Skips comment lines and blank lines
- Non-fatal: any exception is caught and logged
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

# Session-level cache: avoids repeated network calls for the same package
_version_cache: dict[str, str] = {}


class DependencyPinner:
    """Rewrites requirements.txt and package.json with pinned stable versions.

    Parameters
    ----------
    timeout_seconds : int
        Per-package network timeout. Keep short (5s) to avoid blocking pipeline.
    """

    def __init__(self, timeout_seconds: int = 5) -> None:
        self._timeout = timeout_seconds

    def pin_requirements(self, requirements_path: Path) -> int:
        """Pin each dependency in requirements.txt to its latest stable version.

        Returns the number of packages successfully pinned.
        Overwrites the file in-place on success. No-ops on any error.
        """
        if not requirements_path.exists():
            logger.debug("[DependencyPinner] requirements.txt not found at %s", requirements_path)
            return 0

        try:
            lines = requirements_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            logger.warning("[DependencyPinner] cannot read %s: %s", requirements_path, exc)
            return 0

        pinned_lines: list[str] = []
        pinned_count = 0

        for line in lines:
            stripped = line.strip()
            # Pass through comments, blank lines, and already-pinned specs
            if not stripped or stripped.startswith("#"):
                pinned_lines.append(line)
                continue
            # Already pinned exactly — keep as-is
            if "==" in stripped:
                pinned_lines.append(line)
                continue

            pkg = self._extract_package_name(stripped)
            if not pkg:
                pinned_lines.append(line)
                continue

            version = self._resolve_pypi_version(pkg)
            if version:
                pinned_lines.append(f"{pkg}=={version}")
                pinned_count += 1
                logger.debug("[DependencyPinner] pinned %s==%s", pkg, version)
            else:
                # Keep original if resolution fails
                pinned_lines.append(line)

        try:
            requirements_path.write_text("\n".join(pinned_lines) + "\n", encoding="utf-8")
            logger.info(
                "[DependencyPinner] pinned %d/%d packages in %s",
                pinned_count, len(lines), requirements_path.name,
            )
        except Exception as exc:
            logger.warning("[DependencyPinner] cannot write %s: %s", requirements_path, exc)
            return 0

        return pinned_count

    def pin_package_json(self, package_json_path: Path) -> int:
        """Pin '*' and 'latest' dependencies in package.json to resolved versions.

        Returns the number of packages successfully pinned.
        Rewrites package.json in-place on success.
        """
        if not package_json_path.exists():
            logger.debug("[DependencyPinner] package.json not found at %s", package_json_path)
            return 0

        try:
            content = package_json_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as exc:
            logger.warning("[DependencyPinner] cannot parse %s: %s", package_json_path, exc)
            return 0

        pinned_count = 0
        for dep_key in ("dependencies", "devDependencies"):
            deps: dict = data.get(dep_key, {})
            for pkg, version_spec in list(deps.items()):
                if version_spec in ("*", "latest", ""):
                    resolved = self._resolve_npm_version(pkg)
                    if resolved:
                        deps[pkg] = resolved
                        pinned_count += 1
                        logger.debug("[DependencyPinner] pinned npm %s@%s", pkg, resolved)

        try:
            package_json_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
            logger.info(
                "[DependencyPinner] pinned %d npm package(s) in %s",
                pinned_count, package_json_path.name,
            )
        except Exception as exc:
            logger.warning("[DependencyPinner] cannot write %s: %s", package_json_path, exc)
            return 0

        return pinned_count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_package_name(spec: str) -> str:
        """Extract base package name from a requirements spec line."""
        # Strip extras like package[extra]>=1.0
        for sep in (">=", "<=", "!=", "~=", ">", "<", "[", ";"):
            spec = spec.split(sep)[0]
        return spec.strip()

    def _resolve_pypi_version(self, pkg: str) -> str:
        """Return the latest stable version from PyPI JSON API."""
        global _version_cache
        if pkg in _version_cache:
            return _version_cache[pkg]

        try:
            url = f"https://pypi.org/pypi/{pkg}/json"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.load(resp)
            version = data["info"]["version"]
            _version_cache[pkg] = version
            return version
        except urllib.error.HTTPError as exc:
            logger.debug("[DependencyPinner] PyPI HTTP %s for %s: %s", exc.code, pkg, exc)
        except Exception as exc:
            logger.debug("[DependencyPinner] PyPI resolution failed for %s: %s", pkg, exc)
        return ""

    def _resolve_npm_version(self, pkg: str) -> str:
        """Return the latest stable version from npm registry."""
        global _version_cache
        cache_key = f"npm:{pkg}"
        if cache_key in _version_cache:
            return _version_cache[cache_key]

        try:
            url = f"https://registry.npmjs.org/{pkg}/latest"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.load(resp)
            version = data.get("version", "")
            if version:
                _version_cache[cache_key] = version
            return version
        except urllib.error.HTTPError as exc:
            logger.debug("[DependencyPinner] npm HTTP %s for %s: %s", exc.code, pkg, exc)
        except Exception as exc:
            logger.debug("[DependencyPinner] npm resolution failed for %s: %s", pkg, exc)
        return ""

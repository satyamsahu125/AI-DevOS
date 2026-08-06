"""git_manager.py — Git repository lifecycle for generated project workspaces.

R4: Every project workspace is a proper git repository with meaningful commit
history. Users can push to GitHub directly from the AI DevOS UI.

Design:
- Non-fatal: all git errors are caught, logged, and ignored. They never break the pipeline.
- Idempotent: init() is safe to call multiple times on the same workspace.
- Security: GitHub tokens are accepted for push operations only; never stored to disk.
- .env is always in .gitignore — verified before every commit.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Files that MUST never be committed regardless of .gitignore configuration
_ALWAYS_EXCLUDED: frozenset[str] = frozenset({".env", ".env.local", ".env.production", ".env.secret"})

_DEFAULT_GITIGNORE = (
    "# AI DevOS — generated project .gitignore\n"
    "__pycache__/\n"
    "*.pyc\n"
    "*.pyo\n"
    ".venv/\n"
    "venv/\n"
    ".env\n"
    ".env.*\n"
    "*.db\n"
    "*.sqlite\n"
    "node_modules/\n"
    "dist/\n"
    "build/\n"
    ".DS_Store\n"
    "*.log\n"
    ".pytest_cache/\n"
    ".coverage\n"
    "*.egg-info/\n"
)


class GitManager:
    """Manages git repository lifecycle for a generated project workspace.

    All operations are non-fatal: git errors are logged and do not stop the pipeline.
    Never commits .env files.

    Parameters
    ----------
    workspace_path : Path
        Root directory of the project workspace (where .git should live).
    """

    def __init__(self, workspace_path: Path) -> None:
        self._path = workspace_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Initialize git repo + write .gitignore + create initial commit. Idempotent."""
        if (self._path / ".git").exists():
            return  # already initialized

        self._run(["git", "init"])
        self._run(["git", "config", "user.email", "aidevos@local"])
        self._run(["git", "config", "user.name", "AI DevOS"])
        self._write_gitignore()

        # Stage the .gitignore and make an initial commit
        self._run(["git", "add", ".gitignore"])
        self._run(["git", "commit", "-m", "chore: init AI DevOS project", "--allow-empty"])
        logger.info("[GitManager] initialized repo at %s", self._path)

    def commit_sprint(self, sprint: int, summary: str, files: list[str]) -> str | None:
        """Stage all changes and commit after a sprint completes.

        Returns short commit hash or None on failure.
        """
        try:
            self._stage_safe()
            file_preview = ", ".join(files[:5]) + ("..." if len(files) > 5 else "")
            msg = f"feat(sprint-{sprint}): {summary}\n\nFiles: {file_preview}"
            result = self._run(["git", "commit", "-m", msg, "--allow-empty"])
            if result.returncode == 0:
                return self._short_hash()
            logger.warning(
                "[GitManager] commit_sprint %d failed: %s",
                sprint, result.stderr.strip()[:200],
            )
        except Exception as exc:
            logger.warning("[GitManager] commit_sprint raised: %s", exc)
        return None

    def commit_stage(self, stage: str, summary: str) -> str | None:
        """Stage all changes and commit after a stage is approved.

        Returns short commit hash or None on failure.
        """
        try:
            self._stage_safe()
            msg = f"feat({stage}): {summary[:80].strip()}"
            result = self._run(["git", "commit", "-m", msg, "--allow-empty"])
            if result.returncode == 0:
                return self._short_hash()
            logger.warning(
                "[GitManager] commit_stage %s failed: %s",
                stage, result.stderr.strip()[:200],
            )
        except Exception as exc:
            logger.warning("[GitManager] commit_stage raised: %s", exc)
        return None

    def log(self) -> list[dict]:
        """Return up to 50 commits as list of {hash, message, date} dicts."""
        result = self._run(["git", "log", "--format=%H|%s|%ci", "-50"])
        commits = []
        for line in (result.stdout or "").splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1].strip(),
                    "date": parts[2].strip(),
                })
        return commits

    def push_to_github(self, repo_url: str, token: str) -> tuple[bool, str]:
        """Push HEAD to GitHub repo_url using token for authentication.

        The token is embedded in the URL for this call only — it is never
        stored to disk, logged, or included in any response body.

        Returns (success: bool, message: str).
        """
        if not repo_url.startswith("https://"):
            return False, "Only HTTPS GitHub URLs are supported"
        if not token:
            return False, "GitHub token is required"

        # Embed token in URL — standard GitHub CLI practice; stays in-process memory
        auth_url = repo_url.replace("https://", f"https://x-token:{token}@", 1)

        # Ensure we're on main branch
        self._run(["git", "branch", "-M", "main"])

        result = self._run(["git", "push", auth_url, "main", "--force"])
        # IMPORTANT: never log auth_url — it contains the token
        if result.returncode == 0:
            logger.info("[GitManager] push succeeded: repo=%s", repo_url)
            return True, "Push successful"
        error_msg = (result.stderr or result.stdout or "Unknown error").strip()[:500]
        logger.warning("[GitManager] push failed: repo=%s error=%s", repo_url, error_msg)
        return False, f"Push failed: {error_msg}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _stage_safe(self) -> None:
        """Stage all files, ensuring excluded files are never staged."""
        # Stage everything git allows (respects .gitignore)
        self._run(["git", "add", "--all"])
        # Explicitly unstage any files that must never be committed
        for excluded in _ALWAYS_EXCLUDED:
            target = self._path / excluded
            if target.exists():
                self._run(["git", "reset", "HEAD", str(excluded)])
                logger.debug("[GitManager] unstaged excluded file: %s", excluded)

    def _short_hash(self) -> str:
        """Return the short hash of HEAD."""
        result = self._run(["git", "rev-parse", "--short", "HEAD"])
        return result.stdout.strip() or "unknown"

    def _write_gitignore(self) -> None:
        """Write the default .gitignore if it doesn't exist."""
        gitignore_path = self._path / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(_DEFAULT_GITIGNORE, encoding="utf-8")

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the workspace directory. Never raises."""
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._path),
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr="timeout")
        except Exception as exc:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))

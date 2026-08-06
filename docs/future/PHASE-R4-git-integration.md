# Phase R4 — Git Integration

**Timeline:** Week 4–5  
**Depends on:** R3 complete (Dockerfile + CI config in project workspace — makes commit history meaningful)  
**Problem:** Generated files are written to disk but the project workspace is not a git repository. Users get a flat directory with no history, no rollback, no portable export.  
**Outcome:** Every project is a standard git repository with meaningful commit history. Users can push to GitHub and deploy from git.

---

## Why This Matters

Emergent's GitHub sync is one of its most-cited features: "I actually own the code, it's in my GitHub." AI DevOS generates code to disk with zero git history. A developer who wants to take the generated code further has to manually `git init`, figure out what was generated in each sprint, and construct their own history. This is unnecessary friction.

R3 ensures the workspace already has working deployment files. R4 makes the entire project portable.

---

## New Module: GitManager

**File:** `backend/app/workspace/git_manager.py`

```python
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class GitManager:
    """Manages git repository lifecycle for a generated project workspace.
    
    All operations are non-fatal: git errors are logged and do not break the pipeline.
    Never commits .env files or files matching .gitignore patterns.
    """

    def __init__(self, workspace_path: Path) -> None:
        self._path = workspace_path

    def init(self) -> None:
        """Initialize git repo + write .gitignore. Idempotent."""
        if (self._path / ".git").exists():
            return
        self._run(["git", "init"])
        self._run(["git", "config", "user.email", "aidevos@local"])
        self._run(["git", "config", "user.name", "AI DevOS"])
        self._write_gitignore()
        logger.info("[GitManager] initialized repo at %s", self._path)

    def commit_sprint(self, sprint: int, summary: str, files: list[str]) -> str | None:
        """Stage and commit files from a completed sprint. Returns commit hash or None."""
        try:
            self._run(["git", "add", "--all"])
            msg = f"Sprint {sprint}: {summary}\n\nFiles: {', '.join(files[:10])}"
            result = self._run(["git", "commit", "-m", msg, "--allow-empty"])
            if result.returncode == 0:
                hash_result = self._run(["git", "rev-parse", "--short", "HEAD"])
                return hash_result.stdout.strip()
        except Exception as exc:
            logger.warning("[GitManager] commit_sprint failed: %s", exc)
        return None

    def commit_stage(self, stage: str, summary: str) -> str | None:
        """Stage and commit after a single stage approval."""
        try:
            self._run(["git", "add", "--all"])
            result = self._run(
                ["git", "commit", "-m", f"{stage}: {summary[:80]}", "--allow-empty"]
            )
            if result.returncode == 0:
                hash_result = self._run(["git", "rev-parse", "--short", "HEAD"])
                return hash_result.stdout.strip()
        except Exception as exc:
            logger.warning("[GitManager] commit_stage failed: %s", exc)
        return None

    def log(self) -> list[dict]:
        """Return list of commits: {hash, message, date}."""
        result = self._run(
            ["git", "log", "--oneline", "--format=%H|%s|%ci", "-50"]
        )
        commits = []
        for line in (result.stdout or "").splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0][:8], "message": parts[1], "date": parts[2]})
        return commits

    def push_to_github(self, repo_url: str, token: str) -> bool:
        """Push to GitHub. Token is used in-memory only, never stored."""
        # Embed token in URL for authentication (standard GitHub practice)
        auth_url = repo_url.replace("https://", f"https://{token}@")
        result = self._run(["git", "push", auth_url, "main", "--force"])
        return result.returncode == 0

    def _write_gitignore(self) -> None:
        gitignore = (
            "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n*.db\n"
            "node_modules/\ndist/\nbuild/\n.DS_Store\n*.log\n"
        )
        (self._path / ".gitignore").write_text(gitignore)

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(self._path), timeout=30
            )
        except Exception as exc:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))
```

---

## Integration Points

### Project creation
**File:** `backend/app/workspace/manager.py` — `create_workspace()`

After creating the project directory, call:
```python
git_manager = GitManager(workspace_path)
git_manager.init()
```

### After each sprint
**File:** `backend/app/workflow/pipeline_supervisor.py` — after `_run_sprint()` completes

```python
files_written = sprint_result.files_written  # list of paths
summary = f"{len(files_written)} files: {', '.join(f[:3] for f in files_written[:3])}"
commit_hash = git_manager.commit_sprint(sprint_num, summary, files_written)
if commit_hash:
    logger.info("[Pipeline] sprint %d committed: %s", sprint_num, commit_hash)
```

### After major stage approvals
**File:** `backend/app/workflow/engine.py` — in the approval callback

For Architecture, Design, DevOps stages: `git_manager.commit_stage(stage_name, artifact_summary[:80])`

---

## API Endpoints

### GET /projects/{id}/git-log
Returns commit history for the project's workspace:
```json
{
  "commits": [
    {"hash": "abc1234", "message": "Sprint 2: 4 files: auth.py, models.py, routes.py", "date": "2026-08-02 14:30:00 +0000"},
    {"hash": "def5678", "message": "devops: Dockerfile + docker-compose.yml", "date": "2026-08-02 14:20:00 +0000"}
  ]
}
```

### POST /projects/{id}/push-to-github
Body: `{"repo_url": "https://github.com/user/my-app", "token": "ghp_..."}`

The token is used for this request only and never stored in the database.

### GET /projects/{id}/download (update)
Include `.git/` directory in the tar.gz so the downloaded project has full history.

Add `?include_git=false` option for users who only want the code files.

---

## UI Changes

**WorkspacePage:** Add a "Git History" tab showing commit timeline using `GET /projects/{id}/git-log`.

**Project card:** Show commit count badge: "12 commits".

**Export modal:** Two options — "Download with git history (.tar.gz)" and "Push to GitHub" (shows input for repo URL + token).

---

## Security Notes

- The GitHub token is never stored in the database or logged. It is used in-memory for the push operation only.
- `.env` is always in `.gitignore` from init. Double-check before every push that no secrets are staged.
- The download endpoint must never include `.env` in the zip/tar — add explicit exclusion regardless of `.gitignore`.

---

## Exit Criteria

- [ ] Every project workspace has a `.git` directory after creation
- [ ] `GET /projects/{id}/git-log` returns at least one commit per sprint
- [ ] `POST /projects/{id}/push-to-github` pushes successfully to a test GitHub repo
- [ ] Downloaded project (with `include_git=true`) can be cloned locally and `git log` shows full history
- [ ] `.gitignore` excludes `__pycache__`, `.env`, `node_modules`, `*.db`
- [ ] GitHub token is NOT present in any database query, log line, or API response
- [ ] All R1 + R2 + R3 exit criteria still passing

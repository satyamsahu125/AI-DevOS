# Phase R2 — Verifiable Code

**Timeline:** Week 2–3  
**Depends on:** R1 complete (BUG-1 SyntaxError fixed, test suite green)  
**Problem:** "Complete" currently means the LLM said the code is correct. The code is never executed, compiled, or linted before QA approves it.  
**Outcome:** "Complete" means the code parses, dependencies resolve, and lint passes — verified by automated execution, not LLM opinion.

---

## Why This Matters

The single most common failure mode of any code generation system is producing code that looks correct syntactically but fails when run. An LLM reviewer cannot reliably detect missing imports, wrong function signatures, or runtime type errors. Emergent's biggest technical advantage is that generated code is always run before being called done. AI DevOS must match this.

The CodeSandbox was implemented in Phase 5. It has subprocess execution, ruff lint, pytest, eslint, and jest support. It just needs to be enabled and connected to the QA feedback loop.

---

## Changes Required

### 1. Enable sandbox by default

**File:** `backend/.env`
```
SANDBOX_ENABLED=true
SANDBOX_TIMEOUT=60
```

This change alone activates the existing CodeSandbox infrastructure. Subprocess mode (no Docker required) runs ruff + py_compile for Python projects and eslint + node for Node projects.

### 2. Syntax check step after each code generation stage

After `BackendDeveloper` and `FrontendDeveloper` complete a sprint, before the sprint result is saved, run a syntax check:

**New method in CodeSandbox or PipelineSupervisor:**
```python
def _syntax_check(self, project_dir: Path, stack: str) -> list[str]:
    """Run py_compile on every .py file or node --check on every .js file.
    Returns list of error strings, or empty list if all pass."""
    errors = []
    if stack == "python":
        for py_file in project_dir.rglob("*.py"):
            proc = self._run_subprocess(
                ["python", "-m", "py_compile", str(py_file)], cwd=project_dir
            )
            if proc.returncode != 0:
                errors.append(f"{py_file.name}: {proc.stderr.strip()}")
    elif stack == "node":
        for js_file in project_dir.rglob("*.js"):
            proc = self._run_subprocess(
                ["node", "--check", str(js_file)], cwd=project_dir
            )
            if proc.returncode != 0:
                errors.append(f"{js_file.name}: {proc.stderr.strip()}")
    return errors
```

If syntax errors are found, fail the sprint immediately (do not proceed to QA stage). Inject errors into the retry prompt as structured feedback.

### 3. Dependency version pinning

**New module:** `backend/app/workspace/dependency_pinner.py`

After `BackendDeveloper` generates `requirements.txt`, resolve each package against the PyPI JSON API to get the current stable version, and rewrite the file with pinned versions.

```python
import urllib.request, json

def pin_requirements(requirements_path: Path) -> None:
    """Replace unpinned requirements with pinned latest-stable versions."""
    lines = requirements_path.read_text().splitlines()
    pinned = []
    for line in lines:
        pkg = line.split("==")[0].split(">=")[0].strip()
        if not pkg or pkg.startswith("#"):
            pinned.append(line)
            continue
        try:
            url = f"https://pypi.org/pypi/{pkg}/json"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.load(r)
            version = data["info"]["version"]
            pinned.append(f"{pkg}=={version}")
        except Exception:
            pinned.append(line)  # Keep original if resolution fails
    requirements_path.write_text("\n".join(pinned))
```

Cache resolved versions in memory during the session to avoid repeated network calls.

Similarly for `package.json`: resolve each `"*"` or `"latest"` dependency against the npm registry.

### 4. Inject sandbox results into QA stage prompt

**File:** `backend/app/workflow/pipeline_supervisor.py`

The `_run_sandbox()` method already stores results at `sandbox:latest`. The QA stage prompt builder must read this key and include results as a structured section:

```python
# In QA stage context building:
sandbox_json = self._memory_manager.load(f"sandbox:latest:{project_id}")
if sandbox_json:
    context["sandbox_verification"] = sandbox_json
```

**In QA prompt template, add section:**
```
## AUTOMATED VERIFICATION RESULTS
The following checks were run automatically against the generated code:
- Lint errors: {lint_error_count}
- Build: {build_status}
- Tests: {passed}/{total} passed

Specific issues:
{lint_errors_formatted}

Your review MUST address all automated issues. Do not approve code with lint errors or build failures.
```

### 5. Surface verification status in UI

**Frontend — WorkspacePage:**
- Add a `VerificationBadge` component per sprint card
- Fetch sandbox result from `GET /projects/{id}/sandbox-results?sprint={n}`
- Show: ✅ 0 lint errors / ⚠️ 3 errors / ❌ Build failed

**New API endpoint:**
```
GET /projects/{id}/sandbox-results?sprint={n}
→ SandboxResult JSON
```

### 6. Include verification report in download

**File:** `backend/app/api/project.py` — download endpoint

When generating the project zip, include `VERIFICATION_REPORT.md`:
```markdown
# Verification Report — Sprint {N}

## Lint
Errors: {count}
{errors}

## Build
Status: {success/failed}
{errors}

## Tests
Passed: {passed}/{total}
{failures}
```

---

## Exit Criteria

- [ ] `SANDBOX_ENABLED=true` in `.env`
- [ ] A Python file with a deliberate syntax error causes the sprint to fail at verification, not at the LLM QA review
- [ ] `requirements.txt` contains pinned versions (e.g. `fastapi==0.111.0` not `fastapi>=0.100`)
- [ ] QA stage prompt includes a "AUTOMATED VERIFICATION RESULTS" section with real lint error count
- [ ] UI `WorkspacePage` shows verification badge per sprint
- [ ] Downloaded project zip includes `VERIFICATION_REPORT.md`
- [ ] All R1 exit criteria still passing

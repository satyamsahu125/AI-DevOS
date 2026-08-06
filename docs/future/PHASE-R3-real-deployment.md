# Phase R3 — Real Deployment Output

**Timeline:** Week 3–4  
**Depends on:** R2 complete (verified code; pinned dependencies; known-working install path)  
**Problem:** The DevOps stage writes advisory text about deployment ("you should create a Dockerfile..."). It never produces a Dockerfile, docker-compose.yml, or CI config.  
**Outcome:** Every project has a working `docker compose up` command in its README. DevOps stage writes real infrastructure files using the same WriteProjectFilesAction already used for code.

---

## Why This Matters

The gap between "AI DevOS has a DevOps stage" and "AI DevOS produces deployment artifacts" is the gap between a prototype and a product. Emergent deploys a live URL in under 15 minutes. AI DevOS's DevOps stage produces a text document that tells the developer what they should do manually.

R2 gives us exactly what R3 needs: pinned dependency versions (for accurate base image selection and install commands) and a verified working install path (so the Dockerfile's RUN commands actually work).

---

## Changes Required

### 1. Add infra files to FilePlanner schema

**File:** `backend/app/shared/schemas/file_plan_schema.py`

Add a `responsible_stage` field to `PlannedFile` (if not present). Infra files are planned by the FilePlanner but written only when `responsible_stage == "devops"`:

```python
class PlannedFile(BaseModel):
    path: str
    description: str
    operation: Literal["create", "update", "patch"] = "create"
    change_description: str = ""
    responsible_stage: str = "backend_developer"  # default
```

**File:** `backend/app/prompt/file_plan_builder.py`

Add instructions to the FilePlanner prompt to include infra files:
```
For every project, the file plan MUST include:
- Dockerfile (responsible_stage: "devops")
- docker-compose.yml (responsible_stage: "devops")  
- .dockerignore (responsible_stage: "devops")
- .github/workflows/ci.yml (responsible_stage: "devops")
```

### 2. DevOps agent uses WriteProjectFilesAction

**File:** `backend/app/agents/devops_developer.py` (or equivalent)

Currently the DevOps agent calls `generate_text()` and returns a text block. Change it to use `WriteProjectFilesAction` — the same action BackendDeveloper uses — filtered to files where `responsible_stage == "devops"`.

**DevOps agent context input (from R2 outputs):**
- Detected stack (python/node — from FileIndexer)
- Pinned dependency list (from R2 dependency pinner)
- App entry point path (from FileIndexer)
- Port the app listens on (from architecture artifact or detected from code)
- R2 verification result (last working install command)

**Dockerfile template for Python (used as few-shot example in prompt):**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml template:**
```yaml
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///./app.db
    volumes:
      - ./data:/app/data
```

**CI template (.github/workflows/ci.yml):**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: pytest tests/ --tb=short
```

### 3. Verify generated Dockerfile in CodeSandbox

After DevOps stage completes, if Docker is available in the sandbox, run:
```bash
docker build -t aidevos-verify-{project_id} {project_dir} --quiet
```

If Docker is not available, run a syntax check on the Dockerfile using `dockerfile-parse` (pip package) or parse manually.

Either way: inject build result into the DevOps stage result. If build fails, trigger retry with Docker error message as feedback.

### 4. Update RUN_INSTRUCTIONS.md

The existing Document stage generates `RUN_INSTRUCTIONS.md`. Add a section:

```markdown
## Running with Docker (Recommended)

```bash
docker compose up
```

The application will be available at http://localhost:8000

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
```

### 5. Include infra files in download

**File:** `backend/app/api/project.py` — download endpoint

Ensure Dockerfile, docker-compose.yml, .dockerignore, and .github/ directory are included in the project zip. They should already be in the project workspace after R3 — just verify the glob pattern includes dotfiles.

---

## Exit Criteria

- [ ] Generated project directory contains `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/ci.yml`
- [ ] `docker build .` succeeds on the generated Dockerfile (or dockerfile-parse reports no syntax errors if Docker unavailable)
- [ ] `RUN_INSTRUCTIONS.md` lists `docker compose up` as primary command
- [ ] DevOps stage result contains `written_files` list (not a text block)
- [ ] Infra files are included in the project download zip
- [ ] All R1 + R2 exit criteria still passing

# Persistence and Memory Analysis

## QA Result Persistence Pattern (Model for SandboxResult)

Finding: QAAgent persists its findings via `ArtifactStore.write()` with scope `f"sprint_{sprint_number}"` and name `"qa_findings"`. The data dict includes `content` (raw LLM string), `structured` (parsed dict), `stage`, and `written_at` timestamp.

Evidence:
```python
# F:\AI-DevOS3\backend\app\agents\qa.py  lines 163–179
if self._workspace_manager is not None:
    try:
        store = self._workspace_manager.get_artifact_store(project_id)
        store.write(
            scope=f"sprint_{sprint_number}",
            name="qa_findings",
            data={
                "content": response.content,
                "structured": structured,
                "stage": "QA",
                "written_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.warning(
            "[QAAgent.run_sprint_qa] non-fatal ArtifactStore write failure: %s", exc
        )
```

File: `F:\AI-DevOS3\backend\app\agents\qa.py`
Function: `QAAgent.run_sprint_qa()`
Impact: QA results survive process restart — written to `{workspace_root}/{project_id}/artifacts/sprint_{N}/qa_findings.json`. Write is non-fatal.
Recommendation: SandboxResult should follow this exact pattern. Call `workspace_manager.get_artifact_store(project_id).write(scope=f"sprint_{sprint_number}", name="sandbox_result", data=result._to_dict())` immediately after `CodeSandbox.run()` returns.
Confidence: High


## ArtifactStore API

`write()` signature:
```python
def write(self, scope: str, name: str, data: dict, version: bool = False) -> Path
```
- `scope`: "project", "sprint_1", "sprint_2", "release", etc.
- `name`: artifact name without extension (e.g. "qa_findings", "sandbox_result")
- `data`: JSON-serialisable dict
- `version=True`: appends _v2, _v3 ... instead of overwriting

`read()` signature:
```python
def read(self, scope: str, name: str) -> dict | None
```
Returns highest-versioned file, falling back to base file. Returns None on miss.

`list_scope()` signature:
```python
def list_scope(self, scope: str) -> list[str]
```
Returns sorted list of base artifact names (versioned files collapsed to base name).

`exists()` signature:
```python
def exists(self, scope: str, name: str) -> bool
```

On-disk path layout:
```
{workspace_root}/{project_id}/artifacts/
    sprint_1/
        qa_findings.json
        sandbox_result.json   <- where SandboxResult should go
    sprint_2/
        ...
    project/
        version_history.json
```

File: `F:\AI-DevOS3\backend\app\workspace\artifact_store.py`
Confidence: High


## Checkpoint/Recovery System

Finding: A `RecoveryCheckpoint` dataclass and `ExecutionRecovery` class exist, but are **in-memory stubs only** — they do not read or write any files. `ExecutionRecovery.create_checkpoint()` just returns the checkpoint unchanged. No file I/O or database writes are implemented.

Evidence:
```python
# F:\AI-DevOS3\backend\app\execution\execution_recovery.py  lines 16–18
def create_checkpoint(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
    return checkpoint   # no-op stub — nothing is persisted
```

File: `F:\AI-DevOS3\backend\app\execution\execution_recovery.py`
Impact: No checkpoint system exists. After a process restart all in-memory checkpoint state is gone.
Confidence: High


## project.json Contents and Restart Survivability

`project.json` is written atomically (write-to-temp + rename). Fields that survive restart:

| Field | Survives restart? |
|---|---|
| `project_id`, `name`, `description`, `mode` | Yes |
| `state` (ProjectState enum value) | Yes |
| `current_sprint_number` | Yes |
| `total_sprints` | Yes |
| `completed_sprints` (list of ints) | Yes |
| `current_sprint` (Sprint dict) | Yes |
| `sprint_plan` (full SprintPlan dict) | Yes |
| `stages_completed` (list of stage names) | Yes |
| `current_stage` (str or null) | Yes |
| `failed_at_stage`, `failure_reason` | Yes |
| `design_review` dict | Yes |

Evidence:
```python
# F:\AI-DevOS3\backend\app\workspace\manager.py  lines 94–125
payload = {
    "project_id": project_id,
    "current_sprint_number": 0,
    "total_sprints": 0,
    "completed_sprints": [],
    "stages_completed": [],
    "current_stage": None,
    "failed_at_stage": None,
    ...
}
```

`current_sprint_number` IS stored and updated by `set_current_sprint()` (lines 273–293).
File: `F:\AI-DevOS3\backend\app\workspace\manager.py`
Confidence: High


## Sprint-Level Artifact Scope Convention

Finding: The scope string is `f"sprint_{sprint_number}"` — lowercase, underscore separator, 1-indexed integer. Used by both `WorkspaceManager.create_sprint_folder()` and `QAAgent`.

Evidence:
```python
# F:\AI-DevOS3\backend\app\workspace\manager.py  lines 454–459
sprint_dir = (
    self.get_workspace_path(project_id)
    / "artifacts"
    / f"sprint_{sprint_number}"
)

# F:\AI-DevOS3\backend\app\agents\qa.py  line 168
store.write(scope=f"sprint_{sprint_number}", name="qa_findings", ...)
```

Correct scope string for sprint N: `f"sprint_{N}"` (e.g. "sprint_1", "sprint_2")
Confidence: High


## ArtifactStore vs ArtifactManager

These are **two distinct classes** with different purposes:

### ArtifactStore — `F:\AI-DevOS3\backend\app\workspace\artifact_store.py`
- Purpose: Sprint-scoped and phase-scoped JSON artifact persistence (file-only, no DB)
- Constructor: `ArtifactStore(workspace_root: Path, project_id: str)`
- Access: `workspace_manager.get_artifact_store(project_id)` factory method
- Methods: `write()`, `read()`, `exists()`, `list_scope()`, `append_version_audit()`
- Scopes: "project", "sprint_N", "release"
- **Use this for SandboxResult**

### ArtifactManager — `F:\AI-DevOS3\backend\app\artifact\manager.py`
- Purpose: Stage-level artifact persistence with SQLite audit trail and approval workflow
- Constructor: `ArtifactManager(storage_dir, workspace_manager, db_path)`
- Methods: `save_artifact(project_id, stage: Stage, content, structured_content, attempt, ...)`, `get_artifact()`, `list_artifacts()`, `mark_approved()`, `is_approved()`
- Scope: Stage-level only (requires `Stage` enum, e.g. `Stage.Architect`)
- Files written: `{stage}.md`, `{stage}.json`, `{stage}.attempt-N.json`
- **Do NOT use for SandboxResult** — no sprint-scope concept, requires Stage enum

Evidence:
```python
# F:\AI-DevOS3\backend\app\artifact\manager.py  lines 72–83
def save_artifact(
    self,
    project_id: str,
    stage: Stage,          # requires Stage enum — not suitable for sandbox
    content: str,
    structured_content: dict | None = None,
    *,
    attempt: int = 1,
    ...
) -> StageArtifact:
```

Confidence: High


## Summary: Can State Be Reconstructed After Restart?

**Answer: Partial**

What CAN be reconstructed:
- `current_sprint_number` — in `project.json`
- `completed_sprints` list — in `project.json`
- `stages_completed` list — in `project.json`
- `current_stage` — in `project.json`
- Full `sprint_plan` (all sprint definitions, statuses) — in `project.json`
- QA findings — in `artifacts/sprint_N/qa_findings.json` via ArtifactStore
- Stage LLM outputs (architecture, user stories) — in `artifacts/{stage}.json` via ArtifactManager

What CANNOT be reconstructed (gaps):
- **SandboxResult** — held in memory only; `SandboxResult.to_json()` docstring says "storage in MemoryManager" but no ArtifactStore.write() call exists anywhere for sandbox results
- **Whether build/test ran this sprint** — no flag in `project.json`; only inferrable from file presence
- **In-progress stage internal state** — `current_stage` says which stage was running but not how far through it got

Evidence (gap):
```python
# F:\AI-DevOS3\backend\app\shared\dto\sandbox_result.py  lines 98–100
def to_json(self) -> str:
    """Serialize to JSON string for storage in MemoryManager."""
    return json.dumps(self._to_dict(), indent=2)
# to_json() exists but no code calls ArtifactStore.write() with sandbox data anywhere.
```

Gaps summary:
1. SandboxResult is never persisted — disappears on restart
2. No "sandbox_ran" boolean flag in project.json
3. RecoveryCheckpoint / ExecutionRecovery are stubs — no checkpoint files written


## SandboxResult Persistence Recommendation

Exact API call pattern to use, modelled on QAAgent.run_sprint_qa() lines 163–179:

```python
# In the sprint pipeline stage that calls CodeSandbox.run():
result: SandboxResult = code_sandbox.run(project_id, sprint=sprint_number)

# Persist to sprint-scoped ArtifactStore (mirrors QAAgent pattern exactly)
if workspace_manager is not None:
    try:
        store = workspace_manager.get_artifact_store(project_id)
        store.write(
            scope=f"sprint_{sprint_number}",   # matches QAAgent scope convention
            name="sandbox_result",              # new artifact name
            data=result._to_dict(),             # SandboxResult._to_dict() already exists
        )
    except Exception as exc:
        logger.warning(
            "[CodeSandbox] non-fatal ArtifactStore write failure: %s", exc
        )
```

To reload after restart:
```python
store = workspace_manager.get_artifact_store(project_id)
raw = store.read(scope=f"sprint_{sprint_number}", name="sandbox_result")
# raw is the dict from SandboxResult._to_dict()
# Add SandboxResult.from_dict(raw) classmethod to deserialise
```

Idempotency guard (skip sandbox if already ran this sprint):
```python
already_ran = store.exists(scope=f"sprint_{sprint_number}", name="sandbox_result")
```

No additional infrastructure needed. ArtifactStore handles atomic writes and directory creation.
The sprint folder is created by WorkspaceManager.create_sprint_folder() before agents run,
so the directory will always exist when sandbox runs.

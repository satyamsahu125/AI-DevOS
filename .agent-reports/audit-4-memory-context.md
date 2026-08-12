# Audit 4: Memory and Context Architecture

> Auditor: Memory Architecture Auditor  
> Date: 2026-08-11  
> Source: Direct code read — no prior reports trusted  
> Files read: workspace/manager.py, workspace/artifact_store.py, workspace/file_registry.py, artifact/manager.py, memory/manager.py, memory/orchestrator.py (both), intelligence/context_orchestrator.py, intelligence/sprint_monitor.py, intelligence/file_indexer.py, workflow/context_assembler.py, workflow/sprint_executor.py, workflow/middleware/checkpoint.py, session/checkpoint.py, session/manager.py, execution/execution_recovery.py, execution/recovery_checkpoint.py

---

## project.json Fields

**File:** `backend/app/workspace/manager.py`, lines 95–124 (create_workspace)

Fields written at project creation only:
- `project_id` — string UUID
- `name` — display name
- `description` — project description
- `mode` — "full" | "quick" (R9 quick mode flag)
- `created_at` — ISO timestamp set once

Fields set at creation with initial values, then overwritten during execution:
- `original_request` — empty string at creation; populated when clarification phase completes
- `state` — `ProjectState.EMPTY` at creation; updated via `update_state()` at every lifecycle transition
- `updated_at` — set at creation; refreshed on every `update_project_json()` call (line 209)
- `clarification` — `{questions_asked: [], answers_received: [], complete: False}`; updated via `save_qa_questions()` / `save_qa_answer()` / `mark_qa_complete()`
- `sprint_plan` — `None`; written by `update_sprint_plan()` when sprint planning completes
- `current_sprint` — `None`; written by `set_current_sprint()` at start of each sprint
- `current_sprint_number` — `0`; written by `set_current_sprint()`
- `total_sprints` — `0`; written by `update_sprint_plan()`
- `completed_sprints` — `[]`; appended to by `mark_sprint_complete()`
- `stages_completed` — `[]`; updated by engine during stage transitions
- `current_stage` — `None`; updated by engine
- `failed_at_stage` — `None`; written on stage failure
- `failure_reason` — `None`; written on stage failure
- `design_review` — `{status: "pending", user_feedback: None, iteration: 0}`; updated by `update_design_review()`
- `status` — `"active"`; may be updated

Fields added during execution (not present at creation):
- `approved_design` + `design_approved` — written by `save_approved_design()` (line 338–341)
- `qa_session` — written by `save_qa_questions()` (line 382)
- `requirement_changes` — written via `update_project_json()` by agents
- Sprint status fields embedded inside `sprint_plan.sprints[N]`: `status`, `started_at`, `completed_at`

**Persistence:** DISK (`{workspace_root}/{project_id}/project.json`)  
**Survives restart:** YES — written atomically via temp-file + `os.replace()` (lines 213–228)

---

## ArtifactManager

**File:** `backend/app/artifact/manager.py`

**Storage:** Dual — disk files + SQLite index

Disk paths (per `save_artifact()`, lines 89–116):
- `{workspace_root}/{project_id}/artifacts/{stage.value}.md` — latest human-readable artifact (overwritten each call)
- `{workspace_root}/{project_id}/artifacts/{stage.value}.json` — latest structured artifact (overwritten each call)
- `{workspace_root}/{project_id}/artifacts/{stage.value}.attempt-{N}.json` — immutable per-attempt copy (never overwritten)

SQLite table `artifacts` at `memory/memory.db` (schema lines 47–61):
```
id, project_id, stage, file_path, json_path, created_at, attempt, approved
```

**Read API:**
- `get_artifact(project_id, stage)` — reads the canonical `{stage.value}.json` (latest attempt, not sprint-scoped). Returns `StageArtifact | None`.
- `get_artifact_history(project_id, stage)` — returns all attempts ever saved, oldest first, via SQLite ORDER BY attempt ASC.
- `list_artifacts(project_id)` — returns only approved artifacts (latest approved attempt per stage).

**Current vs historical:** YES, can distinguish — `get_artifact()` always returns current (latest file); `get_artifact_history()` returns all attempts. `is_approved()` checks a specific attempt's approval status.

**Sprint scoping:** NONE. `{stage.value}.json` is a single global slot per project. Running the Architect stage in Sprint 3 silently overwrites the Sprint 1 artifact in this slot.

**Note:** A second, separate artifact system exists — `ArtifactStore` (`workspace/artifact_store.py`) — which IS sprint-scoped (`sprint_1/`, `sprint_2/`). The two systems store overlapping data in different locations. Agents use whichever is injected into them.

**Persistence:** DISK + SQLite  
**Survives restart:** YES

---

## MemoryManager

**File:** `backend/app/memory/manager.py`

**Backend:** SQLite at path from env var `MEMORY_DB` (default: `data/memory.sqlite`). Configured at lines 29–49. The repository is `MemoryRepository` backed by a `StorageAdapter` (SQLite driver).

**Key namespace pattern:** `{project_id}:{key}` (line 63: `f"{project_id}:{key}"`)

**Keys stored in practice** (from callers across the codebase):
- `{project_id}:workflow:stage:{stage_name}` — approved stage output (via `store_stage_output()`, line 98)
- `{project_id}:workflow:latest_message` — `WORKFLOW_MESSAGE_KEY` constant — predecessor agent message
- `{project_id}:design:approved` — `DESIGN_MEMORY_KEY` — approved design spec (context_assembler.py line 268)
- `{project_id}:gate:feedback:{gate_name}` — human gate feedback (context_assembler.py line 325)
- `{project_id}:workflow:rejection:{stage.value}` — stage rejection record (memory/orchestrator.py line 133)
- `{project_id}:sandbox:latest` — latest sandbox execution result (context_assembler.py line 349)

**Legacy migration:** On first DB creation, scans for `*.txt` files in root directory and imports them (lines 126–148). Pre-dates project namespacing — migrated records use un-namespaced keys.

**Persistence:** DISK (SQLite)  
**Survives restart:** YES

---

## ContextOrchestrator / ContextAssembler

**Files:** `backend/app/intelligence/context_orchestrator.py`, `backend/app/workflow/context_assembler.py`, `backend/app/memory/orchestrator.py`

### Sprint Filtering

**ContextOrchestrator** (`_load_stage_artifacts`, lines 229–258): Loads stage artifacts using `_STAGE_NEEDS` map — calls `ArtifactManager.get_artifact(project_id, stage_enum)` which reads the global canonical `{stage.value}.json`. **No sprint number is passed. No sprint filter exists.** A Sprint 3 BackendDeveloper receives the same Architect artifact whether it was written in Sprint 1 or Sprint 3.

**MemoryOrchestrator._load_predecessor_outputs** (memory/orchestrator.py lines 182–200): Iterates ALL stages in `Stage` enum order up to the current stage, loading `memory_manager.load_stage_output(project_id, s.value)`. This is the `workflow:stage:{stage_name}` key — a **single global slot per stage per project, not per sprint**. Sprint 3 BackendDeveloper will receive Sprint 1 QA findings, Sprint 1 SprintDeploy notes, etc., as predecessor outputs.

**SprintMonitor.generate_sprint_brief** (intelligence/sprint_monitor.py line 67): Does filter by sprint — `previous_files = [f for f in built_files if f.sprint_number < sprint_number]`. This provides file-level cross-sprint awareness. This is the ONLY place sprint-number filtering exists.

### Recency Filtering

None. There is no TTL, timestamp gate, or recency filter on artifact or episodic memory reads.

### Staleness Risk

YES — confirmed. The following code path shows how Sprint 1 QA artifacts reach Sprint 3 BackendDeveloper context:

1. `ContextAssembler.assemble("BackendDeveloper")` calls `_assemble_via_orchestrator()`
2. Which calls `memory_orchestrator.get_context(project_id, Stage.BackendDeveloper)`
3. Which calls `_load_predecessor_outputs()` — iterates all stages in enum order
4. `load_stage_output(project_id, "QA")` reads key `{project_id}:workflow:stage:QA` — returns Sprint 1 QA output verbatim
5. This becomes `ctx.predecessor_outputs["QA"]` — injected into Sprint 3 BackendDeveloper prompt with no sprint label

**Evidence:** `memory/orchestrator.py` lines 183–200; `memory/manager.py` lines 101–103

---

## CheckpointManager / ExecutionRecovery

Two separate mechanisms exist with very different implementations.

### CheckpointManager (REAL IMPLEMENTATION)

**File:** `backend/app/session/checkpoint.py`

Fully implemented. Persists `SessionCheckpoint` to SQLite table `session_checkpoints` at `memory/memory.db`.

Schema (lines 53–68):
```sql
session_id TEXT PRIMARY KEY
stage TEXT NOT NULL
project_id TEXT NOT NULL
attempt_number INTEGER NOT NULL
decisions_made TEXT NOT NULL   -- JSON array
remaining_work TEXT NOT NULL   -- JSON array
failed_approaches TEXT NOT NULL -- JSON array
last_artifact_summary TEXT NOT NULL
saved_at TEXT NOT NULL
```

Real methods: `save()` (UPSERT, lines 72–103), `restore()` (line 105), `delete()` (line 117), `list_incomplete()` (line 144), `cleanup_old_checkpoints()` (line 123).

Used by `CheckpointMiddleware` (workflow/middleware/checkpoint.py) which saves before each LLM attempt and deletes on clean exit.

**Persistence:** DISK (SQLite)  
**Survives restart:** YES — `list_incomplete()` is the crash-recovery signal

**Gap:** No auto-resume path. CheckpointMiddleware.report_incomplete() logs the incomplete sessions (line 35–40), but no code reads the checkpoint and resumes the pipeline from that stage+attempt. Recovery is detection-only, not automatic restart.

### ExecutionRecovery (STUB)

**File:** `backend/app/execution/execution_recovery.py`

`create_checkpoint()` is a stub. Exact code:

```python
def create_checkpoint(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
    return checkpoint
```

It receives a `RecoveryCheckpoint` dataclass and immediately returns it unchanged. No disk write. No SQLite insert. No file write. The `resume()` and `recover()` methods call `self.validation.validate(checkpoint)` and return `RecoveryResult(success=True, ...)` without restoring any state.

`RecoveryCheckpoint` is also a pure dataclass (execution/recovery_checkpoint.py) with no persistence logic.

**Implemented:** NO (stub)  
**Evidence:** `execution/execution_recovery.py` lines 16–17

---

## FileRegistry

**File:** `backend/app/workspace/file_registry.py`

**Storage:** `{workspace_root}/{project_id}/artifacts/file_registry.json` (line 121: `ws_path / "artifacts" / _REGISTRY_FILENAME`)

**Fields per entry** (lines 56–62):
- `path` (str) — normalized forward-slash path, e.g. `"backend/models/user.py"`
- `created_sprint` (int) — sprint number when file was first created
- `last_updated_sprint` (int) — sprint number of most recent write

**No `deleted` flag.** Evidence: `record()` method lines 46–65 — only sets `created_sprint` and `last_updated_sprint`. No deletion marker exists in the schema.

**No `requirements_version` field.** Not in the dataclass, not in the record dict.

**When Sprint 2 regenerates a Sprint 1 file:** `record()` checks `if key in registry` (line 55) — if present, updates only `last_updated_sprint`. The `created_sprint` is preserved. The entry is updated in-place; no historical entry is created. No delta or patch record is kept.

**Persistence:** DISK (JSON file)  
**Survives restart:** YES

---

## Post-Crash Recovery Path

### What survives on disk after a mid-sprint crash

- `project.json` — project state, sprint plan, `completed_sprints`, `current_sprint_number` (atomic write; if crash happened during the rename, worst case is loss of one update, not corruption)
- `artifacts/{stage.value}.json` and `.md` — every stage artifact written before the crash
- `artifacts/{stage.value}.attempt-{N}.json` — all attempt files (immutable, append-only)
- `artifacts/file_registry.json` — which files were written and which sprint wrote them
- `artifacts/sprint_N/` directory — sprint-scoped ArtifactStore files
- `data/memory.sqlite` — all stage outputs, gate feedback, rejection records, sandbox results
- `memory/memory.db` — SQLite session_checkpoints table (crash = incomplete checkpoint left behind) and artifacts table
- `FileIndexer` SQLite database — project file index with sprint numbers
- Actual generated source files in the project workspace

### What is lost

- Active `SessionManager._sessions` dict (in-memory, `session/manager.py` line 24) — all in-flight session state is gone
- Any LLM response being streamed that had not been written to disk
- Any `memory_manager.store()` call that was mid-transaction at the Python level (SQLite WAL protects against partial writes)

### Can the pipeline resume correctly without re-running completed stages

**PARTIAL.** The data to resume exists (project.json `completed_sprints`, on-disk stage artifacts, SQLite checkpoint records). However:

1. `CheckpointMiddleware.report_incomplete()` detects the incomplete session and logs it (middleware/checkpoint.py lines 31–41)
2. No code path re-reads those checkpoints and restarts the pipeline from the correct stage+attempt
3. The pipeline would have to be re-triggered from scratch via the API
4. On re-trigger, `completed_sprints` in project.json would allow PipelineSupervisor to skip already-completed sprints (if that guard is implemented), but in-progress sprint stages would re-run from the first stage

**In practice:** Completed sprints survive. In-progress sprint stages re-run from stage 1 of that sprint, potentially re-generating files that were partially written. No data corruption risk because stage artifact writes overwrite the previous file.

---

## Context Contamination Risk

### Scenario: Sprint 1 architecture is superseded in Sprint 3

**Case A: Architect stage does NOT re-run in Sprint 3 (common)**

Sprint 3 agents receive Sprint 1's Architect artifact unchanged. This is intentional — architecture is a project-level document meant to persist. No contamination issue here; it is correct design behavior.

**Case B: Architect stage re-runs in Sprint 3**

1. `ArtifactManager.save_artifact(project_id, Stage.Architect, ...)` called
2. Overwrites `artifacts/Architect.json` (single global slot)
3. Sprint 3 agents that call `get_artifact(project_id, Stage.Architect)` now receive Sprint 3 architecture
4. Sprint 1 architecture is gone from the primary slot (only `Architect.attempt-N.json` preserves it)
5. No agent is notified of the change; any Sprint 3 stage that already assembled its context before the overwrite received Sprint 1 architecture

**Case C: Sprint 1 QA / deploy artifacts contaminating Sprint 3 developer context**

Full trace (the real contamination path):

1. Sprint 1 QA stage completes → `memory_manager.store_stage_output(project_id, "QA", qa_output)` stores key `{project_id}:workflow:stage:QA`
2. Sprint 3 begins → `ContextAssembler.assemble("BackendDeveloper")` called
3. → `_assemble_via_orchestrator()` → `memory_orchestrator.get_context(project_id, Stage.BackendDeveloper)`
4. → `_load_predecessor_outputs()` iterates all stages; finds "QA" precedes "BackendDeveloper" in Stage enum
5. → `memory_manager.load_stage_output(project_id, "QA")` returns Sprint 1 QA output (single slot, not sprint-scoped)
6. Sprint 3 BackendDeveloper prompt includes Sprint 1 QA findings labeled as predecessor output
7. Sprint 3 BackendDeveloper may make decisions based on Sprint 1 QA data that is stale or contradicted by Sprint 3 scope

**Evidence:** `memory/orchestrator.py` lines 183–200; `memory/manager.py` lines 91–103

**Staleness risk: YES** — confirmed. The severity depends on whether QA findings from Sprint 1 are still relevant in Sprint 3. For orthogonal sprints (e.g., Sprint 1: auth, Sprint 3: reporting), Sprint 1 QA output injected into Sprint 3 context is noise at best, misleading at worst.

---

## Memory Architecture Summary Table

| Component | What it stores | Persistence | Survives restart | Staleness risk |
|-----------|---------------|-------------|-----------------|----------------|
| `project.json` | Project lifecycle state, sprint plan, clarification, design review | DISK (atomic JSON) | YES | LOW — always current |
| `ArtifactManager` (disk) | Stage artifacts as `.json`/`.md`/`.attempt-N.json` | DISK | YES | MEDIUM — single global slot per stage; sprint N overwrites sprint 1 silently |
| `ArtifactManager` (SQLite) | Artifact audit rows (project_id, stage, attempt, approved) | DISK (SQLite) | YES | LOW — append-only history |
| `ArtifactStore` | Sprint-scoped and project-scoped JSON artifacts | DISK | YES | LOW — scoped by sprint directory |
| `MemoryManager` / SQLite | Key/value stage outputs, gate feedback, design, sandbox results | DISK (SQLite) | YES | HIGH — single slot per stage; no sprint scoping; Sprint 1 outputs persist through Sprint N |
| `FileRegistry` | Per-project file manifest with created/updated sprint numbers | DISK (JSON) | YES | LOW — cumulative, accurate |
| `FileIndexer` | Per-file parsed metadata (classes, functions, imports, sprint_number) | DISK (SQLite) | YES | LOW — UPSERT by (project_id, file_path) |
| `CheckpointManager` | Session checkpoints (stage, attempt, failed_approaches) | DISK (SQLite) | YES | N/A — crash detection only |
| `SessionManager` | Active session objects | IN-MEMORY dict | NO | N/A — ephemeral by design |
| `ExecutionRecovery` | Recovery checkpoints | NONE (stub) | NO | N/A — unimplemented |
| `MemoryOrchestrator` (memory/) | In-memory index + cache overlay over repository | IN-MEMORY | NO | N/A — cache layer |
| `KnowledgeMemory` / `LessonStore` | Cross-project patterns and lessons | DISK (.hnsw + SQLite) | YES | LOW — additive; filtered by score threshold |

---

## Critical Gaps

1. **No sprint-scoped episodic memory.** `MemoryManager.store_stage_output()` writes to key `{project_id}:workflow:stage:{stage_name}` — a single slot. Sprint 3 stage outputs overwrite Sprint 1 outputs. `_load_predecessor_outputs()` loads all predecessor stages with no sprint filter, so every Sprint N agent receives outputs from Sprint 1 stages verbatim. Fix: key by `{project_id}:sprint:{N}:stage:{stage_name}` and filter by `current_sprint_number - 1` or `all_sprints <= N`.

2. **ExecutionRecovery.create_checkpoint() is a stub.** `execution/execution_recovery.py` line 16–17: `return checkpoint` with no persistence. `RecoveryCheckpoint` is a pure dataclass that never touches disk. The real checkpoint mechanism (CheckpointManager / session/checkpoint.py) is separate and works, but `ExecutionRecovery` — which appears to be the intended unified recovery API — does nothing. Any caller depending on `ExecutionRecovery` instead of `CheckpointManager` gets no crash safety.

3. **Crash detection without auto-resume.** `CheckpointManager.list_incomplete()` correctly identifies crashed sessions on restart, and `CheckpointMiddleware.report_incomplete()` logs them. However, no code path reads those records and restarts the pipeline from the interrupted stage+attempt. Recovery requires a manual re-trigger of the project; there is no automated resume.

4. **FileRegistry has no `deleted` flag.** When a file is removed between sprints (Sprint 2 drops a file Sprint 1 created), the registry entry persists indefinitely. `to_prompt_summary()` will present the deleted file to `FileStructurePlanner` as an existing file requiring `update`, causing the planner to generate patches for a file that no longer exists.

5. **Two artifact storage systems with no cross-referencing.** `ArtifactManager` (artifact/manager.py) and `ArtifactStore` (workspace/artifact_store.py) both store stage artifacts but in different paths, with different APIs, and different sprint semantics. `ArtifactManager` has a single global slot per stage. `ArtifactStore` is sprint-scoped. Agents and orchestrators choose whichever is injected; the same logical artifact (e.g., Architect output) may exist in both locations at different versions with no reconciliation.

6. **ContextOrchestrator._STAGE_NEEDS is hard-coded and does not include sprint stages.** The `_STAGE_NEEDS` dictionary lists prerequisites for named stages but contains no sprint-number-aware entries. A sprint 3 `BackendDeveloper` and a sprint 1 `BackendDeveloper` receive identical prerequisite lookups, despite potentially needing different prior-sprint context.

7. **SessionManager is entirely in-memory.** `session/manager.py` line 24: `self._sessions: dict[str, StageSession] = {}`. Every active session is lost on process restart. While CheckpointManager captures the stage+attempt, the `StageSession` object (retry_count, state) must be reconstructed from scratch. There is no hydration path from checkpoint to restored session.

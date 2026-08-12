# Audit 6: Repository Integrity Audit

## FileRegistry Schema

**Fields per entry (3 fields, all scalars):**
| Field | Type | Description |
|---|---|---|
| `path` | str | Normalized file path (forward-slash, no leading slash) |
| `created_sprint` | int | Sprint number on which the file was first written |
| `last_updated_sprint` | int | Sprint number of the most recent write |

**Missing fields:**
- No `deleted` flag — entries are never tombstoned or removed
- No `requirement_id`, `feature_id`, `story_id` — no linkage to requirements or user stories
- No `owner`, `agent`, `stage`, or `module` metadata
- No `size`, `hash`, or content fingerprint
- No `operation_history` — only the latest sprint numbers, not a full write log

**Evidence:**
- `F:\AI-DevOS3\backend\app\workspace\file_registry.py` lines 56–62 (the `record()` method constructs exactly these three fields)
- Storage format: `{workspace_root}/{project_id}/artifacts/file_registry.json` (line 10, 116–121)

---

## File Ownership / Traceability

**Can answer "which files implement requirement X": NO**

There is no field in `FileRegistry`, `FileIndexer`, or any schema that links a file path to a `req_id` or `story_id`. The pipeline produces `RequirementsArtifact` (with `req_id` fields, schema line 18) and `FileRegistry` (with sprint fields) as completely separate artifacts with no cross-reference.

**Can answer "which files were created in sprint N": PARTIAL (manual filtering only)**

`FileRegistry.list_all()` returns all entries with `created_sprint` and `last_updated_sprint` fields; callers can filter by those values. There is no dedicated `get_files_by_sprint(n)` method. `FileIndexer` stores `sprint_number` (the sprint in which the file was last indexed) in SQLite, and `get_project_index()` returns all rows — also requires manual filtering.

**Evidence:**
- `file_registry.py` lines 85–91 (`list_all()` returns raw list; no sprint-filter parameter)
- `file_indexer.py` lines 51–71 (SQLite schema: `sprint_number INTEGER DEFAULT 0`; no query method by sprint)
- `requirements_schema.py` lines 17–18, 39–40 (req_id and story_id fields exist in requirements but are never stored in file metadata)

---

## Sprint Overwrite Behavior

When Sprint 2 regenerates a file that Sprint 1 created (e.g., `backend/auth.py`):

1. `WriteProjectFilesAction.run()` calls `self.file_registry.record(project_id, planned_file.path, sprint_number=2)` after writing the file (line 197 of `write_project_files.py`).
2. `FileRegistry.record()` checks `if key in registry` — the key exists — so it executes only `registry[key]["last_updated_sprint"] = sprint_number` (line 56 of `file_registry.py`).
3. `created_sprint` is NOT modified — it remains 1.
4. `last_updated_sprint` is updated to 2.

**This behavior is correct and intentional.** The design comment on line 50 of `file_registry.py` explicitly documents: "On first write: sets created_sprint and last_updated_sprint. On subsequent writes: updates last_updated_sprint only."

**Evidence:**
- `file_registry.py` lines 46–65 (`record()` method)
- `write_project_files.py` line 197 (call site)

---

## Feature Removal / File Deletion

**Verdict: NOT IMPLEMENTED**

No code path anywhere in the pipeline deletes a generated project file from disk when a feature is removed or deprecated.

**Trace of what does exist:**

1. `ImpactAnalyzer.analyze()` (`impact_analyzer.py` lines 100–176) handles `remove_feature` change type by marking stages (`product_owner`, `architect`, `file_planner`, `backend`, `frontend`, `qa`, `document`) as needing re-run. It does NOT delete any files.
2. `ImpactAnalyzer.analyze_file_impact()` (lines 178–230) identifies `files_to_regenerate` using `FileIndexer` + `DependencyGraph`. It returns a list of paths — it does NOT delete or remove them.
3. `WorkspaceManager.delete_workspace()` (`manager.py` line 140–146) deletes the entire workspace via `shutil.rmtree` — a project-level wipe, not targeted file removal.
4. The grep for `delete_file`, `remove_file`, `unlink` across the app directory finds: only `project/repository.py` line 49 (artifact cleanup), `workspace/manager.py` line 225 (temp file cleanup in atomic writes), and `syntax_validator.py` line 141 (temp file cleanup). None of these touch generated project files.
5. `FileRegistry` has no `delete()` or `mark_deleted()` method — entries can never be removed from the registry.

When Sprint 2's `SprintDeltaPlanner` produces `FileOperationDecision` entries, the only valid operations are `create`, `update`, and `patch` (`sprint_delta_schema.py` line 10). There is no `delete` operation.

**Evidence:**
- `sprint_delta_schema.py` line 10
- `impact_analyzer.py` lines 43–53, 196–230
- `file_registry.py` — no `delete`, `remove`, or `mark_deleted` method anywhere in the class

---

## Orphaned File Detection

**NOT IMPLEMENTED**

No component scans the filesystem and cross-references it against the sprint plan or FileRegistry to detect files that are no longer referenced.

`ProjectDependencyGraph.get_entry_points()` (`dependency_graph.py` lines 77–81) identifies files that nothing else imports (i.e., no other file depends on them). This is related but different: an entry point is a legitimate top-level file; an orphan would be a file no longer referenced by any requirement or sprint plan. These are not the same check, and `get_entry_points()` is only called in the context of graph analysis, not integrity checking.

`FileIndexer.get_project_index()` returns all indexed files, but nothing compares that set against the current sprint plan's file list to find stranded paths.

**Evidence:**
- `dependency_graph.py` lines 77–81 (`get_entry_points()` — not an orphan scanner)
- `file_indexer.py` — no `find_orphans()`, `scan_stale()`, or filesystem-comparison method
- No call site anywhere in the app that performs "disk files minus plan files" set arithmetic

---

## GitManager Behavior

**Commits:** `commit_sprint()` (`git_manager.py` lines 80–98) calls `_stage_safe()` which runs `git add --all` (line 168), then commits with a message `feat(sprint-{N}): {summary}`. `git add --all` stages all changes including file deletions that git was already tracking — so if a previously-committed file is manually deleted from disk, the deletion will appear in the next commit. However, since the pipeline never deletes files (see Feature Removal above), this path is never triggered in practice.

**Tracks deletions: CONDITIONAL**

`git add --all` (not `git add -A` but equivalent) does stage git-tracked deletions if they occur on disk. The `_stage_safe()` method also explicitly unstages four hardcoded `.env` filenames (lines 169–173). No explicit `git rm` calls exist. Deletions are only implicitly tracked if (a) a file was previously committed and (b) it is then deleted from disk — which the pipeline never does autonomously.

**Rollback: NO**

There is no `rollback()`, `revert()`, `reset_hard()`, or `checkout_previous()` method in `GitManager`. The only branch operation is `git branch -M main` inside `push_to_github()` (line 150). The `log()` method provides read-only history but no way to restore a prior state programmatically.

**Evidence:**
- `git_manager.py` lines 65–98 (`init()`, `commit_sprint()`), lines 165–174 (`_stage_safe()`), lines 133–159 (`push_to_github()`)
- No `rollback`-related method anywhere in `GitManager`

---

## Import Consistency

**Static analysis exists but is NOT connected to deletion or integrity checks.**

`FileIndexer._parse_python()` uses `ast.parse` to extract all imports from Python files (lines 276–311). `FileIndexer._parse_js()` uses regex to extract JS/TS imports (lines 313–339). Both populate `dependencies` (project-internal imports only).

`ProjectDependencyGraph.get_impact()` (lines 48–68) performs BFS over the reverse dependency graph to find all files that transitively depend on a given file. This can answer "if `payroll.py` is deleted, which files will have broken imports."

**However:** This analysis is never invoked proactively. It is only called by `ImpactAnalyzer.analyze_file_impact()` in response to a user-initiated requirement change. There is no background check, no pre-commit hook, and no pipeline step that scans for broken imports after a sprint completes.

If `payroll.py` were deleted from disk (which the pipeline cannot do autonomously), any file importing it would still be written with that import — the LLM generating sibling files receives the written siblings list as context but no validation that the imported files actually exist on disk.

**Evidence:**
- `file_indexer.py` lines 276–339 (AST + regex parsing)
- `dependency_graph.py` lines 48–68 (`get_impact()`)
- `impact_analyzer.py` lines 178–230 (`analyze_file_impact()` — only called on demand)
- No call to `get_impact()` or import validation inside `write_project_files.py` or any sprint-execution code path

---

## File-to-Requirement Mapping

**Exists: NO**

There is no bidirectional (or unidirectional) map from file paths to user stories or requirements at any layer of the system.

`RequirementsArtifact` (`requirements_schema.py` lines 17–18, 39–40) holds `req_id` (e.g., `REQ-001`) and `story_id` (e.g., `US-001`) as part of the requirements stage output. These IDs exist only in the `requirements` artifact JSON and in sprint planning prompts. They are never stored in:
- `FileRegistry` entries (3 fields: path, created_sprint, last_updated_sprint only)
- `FileIndexer` rows (no req_id column in SQLite schema, lines 52–71)
- `FilePlanArtifact` / `PlannedFile` schema (`file_plan_schema.py` lines 8–18: path, module, purpose, responsible_stage, operation, change_description — no req_id)
- `FileOperationDecision` in `SprintDeltaArtifact` (`sprint_delta_schema.py` lines 6–13: path, operation, rationale, change_description, responsible_stage — no req_id)

**Consequence for requirement change:** When a requirement changes, `ImpactAnalyzer` uses keyword-based heuristics (`CodeSummarizer.get_relevant_files()`) to guess which files are relevant. There is no lookup of "files tagged with req_id=REQ-042." The system cannot deterministically identify which files implement a specific requirement without relying on LLM semantic similarity.

**Evidence:**
- `file_registry.py` lines 56–62 (schema)
- `file_indexer.py` lines 52–71 (SQLite schema)
- `file_plan_schema.py` lines 8–18 (`PlannedFile` — no req_id)
- `sprint_delta_schema.py` lines 6–13 (`FileOperationDecision` — no req_id)
- `impact_analyzer.py` lines 205–212 (keyword-based file relevance, not structured mapping)

---

## Sprint File Plan Persistence

**YES — the FilePlanArtifact is persisted and survives restarts.**

`WriteFilePlanAction.run()` returns an `ActionOutput` with `structured` content. The workflow engine calls `ArtifactManager.save_artifact()` which writes two files:
- `{workspace_root}/{project_id}/artifacts/file_structure_planner.json` — the canonical latest version (JSON, includes structured content)
- `{workspace_root}/{project_id}/artifacts/file_structure_planner.md` — markdown version
- `{workspace_root}/{project_id}/artifacts/file_structure_planner.attempt-{N}.json` — versioned history copy

`ArtifactManager.get_artifact(project_id, Stage.FileStructurePlanner)` reads the `.json` file from disk and returns the structured content (lines 160–180 of `artifact/manager.py`). This works across process restarts because it reads from the filesystem, not memory.

`WriteSprintDeltaAction._load_prior_file_plan()` (`write_sprint_delta.py` lines 163–178) calls exactly this method to load the previous sprint's file plan, confirming the persistence is actively used.

**Evidence:**
- `artifact/manager.py` lines 89–94 (file paths written), lines 160–180 (`get_artifact()` reads from disk)
- `write_sprint_delta.py` lines 163–178 (cross-sprint load of persisted plan)
- `write_file_plan.py` lines 264–311 (`run()` — produces the artifact that gets saved)

---

## Repository Integrity Summary

### What the system CAN maintain:
- Sprint-level file provenance: which sprint first wrote each file, which sprint last updated it
- File content indexing: classes, functions, imports, exports, dependencies (via FileIndexer SQLite)
- Git commit history: one commit per sprint, staged with `git add --all`
- Dependency graph: which files transitively import which other files
- Sprint file plan persistence: FileStructurePlanner output survives restarts
- Operation semantics: create/update/patch distinctions enforced by SprintDeltaPlanner + FileRegistry

### What the system CANNOT maintain:
- File-to-requirement linkage: no way to answer "which files implement REQ-042"
- File deletion on feature removal: removed features leave stale files on disk permanently
- Orphaned file detection: no scanner compares disk state to active sprint plan
- Broken import detection: not run proactively; only available on-demand via ImpactAnalyzer
- Registry tombstoning: FileRegistry entries are immortal; no deleted flag
- Git rollback: no programmatic way to restore a prior workspace state

### Critical Gaps (numbered)

1. **No file deletion on feature removal.** When a user requests "remove payroll," the pipeline can mark stages for re-run but no code path removes `payroll/routes.py` or any other file from disk. Stale code accumulates across sprints indefinitely.

2. **No file-to-requirement mapping.** `req_id` and `story_id` exist in the requirements artifact but are never stored in FileRegistry, FileIndexer, or the file plan schema. Requirement-change impact on specific files is guessed by keyword similarity, not by a structured lookup. If a requirement is removed, the system cannot enumerate which files were created to implement it.

3. **No orphaned file detection.** No component compares the set of files on disk (or in FileIndexer) against the set of files referenced in any current sprint plan or requirement. Files from cancelled features accumulate silently.

4. **No broken import detection on file removal.** While `ProjectDependencyGraph.get_impact()` could identify import-broken files, it is never called as part of a sprint integrity check. If a module is logically removed, its importers remain unrepaired.

5. **No git rollback.** `GitManager` has no `rollback()` or `revert()` method. Sprint failures cannot be undone at the git level; the only recovery is a full workspace deletion (`delete_workspace()`).

6. **FileRegistry entries are permanent.** There is no `delete()` or `mark_deleted()` method. A file removed from disk (e.g., manually or by future deletion logic) remains in the registry indefinitely, causing future sprint prompts to include it as an "existing file" in the `to_prompt_summary()` output, potentially confusing the LLM into treating a non-existent file as updatable.

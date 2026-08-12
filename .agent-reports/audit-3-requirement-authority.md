# Audit 3: Requirement Authority Audit

**Auditor:** Requirements Authority Subagent  
**Date:** 2026-08-10  
**Scope:** Can a newly-started agent reliably determine the CURRENT authoritative project requirements?

---

## original_request Storage and Mutability

**Finding:** `original_request` is stored as a top-level string field in `project.json`. It is initialized to `""` at workspace creation and written on the first `WorkflowManager.run()` call. It is NOT updated when a requirement change is applied via `ChangeManager.apply()`. There is no history of prior `original_request` values, no `original_request_v2`, and no `original_request_superseded_at`.

**Evidence:**

- `workspace/manager.py` line 100: `"original_request": ""` — initialized empty at workspace creation.
- `workflow/manager.py` line 214: `self.workspace_manager.update_project_json(project_id, {"original_request": request})` — written when `run()` is called with a non-empty `request`.
- `workflow/change_manager.py` lines 132–145: `ChangeManager.apply()` appends to `requirement_changes` list in `project.json` but does NOT touch `original_request`.

**Impact:** A newly-started agent reads `original_request` and receives the initial project brief, not the current amended requirements. If the user changed requirements in Sprint 3, the agent sees the Sprint 1 description as the "request." The `requirement_changes` list provides a partial audit trail but no structured "current requirement" superseding the original.

---

## Requirement Versioning

**Finding:** There is NO dedicated requirement versioning model. The `RequirementChange` schema captures change metadata (`change_id`, `description`, `change_type`, `affected_feature`, `submitted_at`) but does NOT record: (a) the previous requirement text, (b) the new requirement text, (c) which artifact version was superseded, or (d) approval status. The `requirement_changes` array in `project.json` is an append-only log of change descriptions, not a versioned diff.

**Evidence:**

- `shared/schemas/requirement_change_schema.py` lines 7–14: `RequirementChange` has `change_id`, `project_id`, `submitted_at`, `description`, `change_type`, `affected_feature`. No `previous_requirement`, `current_requirement`, `superseded_artifact_version`, or `approved_by`.
- `workflow/change_manager.py` lines 133–145: Each applied change appends `{"change_id", "description", "applied_at", "comment", "stages_rerun"}` to `requirement_changes`. This is the entire requirement history.
- There is no `RequirementVersion`, `RequirementHistory`, or similar model anywhere in `backend/app/shared/models/` or `backend/app/shared/schemas/`.
- `ArtifactStore.append_version_audit()` (`workspace/artifact_store.py` lines 213–269) provides artifact-level audit for `user_stories` and `architecture` updates, but only captures the reason string (truncated to 200 chars), not the before/after content.

**Impact:** An agent cannot reconstruct what the requirements were before a change, cannot determine what specifically changed, and cannot verify whether the current user stories in `project/user_stories.json` reflect Sprint 1 or Sprint 3 requirements without reading the full change description strings.

---

## Architecture Decision Validity

**Finding:** Architecture artifacts are written through TWO separate, non-synchronized persistence paths. Validity cannot be determined from either path alone.

**Path A — ArtifactManager (flat file, always-latest):**
`ArtifactManager.save_artifact()` writes `artifacts/{stage.value}.json` (overwriting) and `artifacts/{stage.value}.attempt-{N}.json` (history). `get_artifact()` reads the flat `artifacts/Architect.json`.

**Path B — ArtifactStore (versioned files in project/ scope):**
`ArchitectAgent.update_architecture()` writes `artifacts/project/architecture_v2.json`, `_v3.json`, etc. via `ArtifactStore.write(..., version=True)`. `ArtifactStore.read()` returns the highest-versioned file.

These two paths write to different directories (`artifacts/` vs. `artifacts/project/`) and are never synchronized. An agent using `ArtifactManager.get_artifact()` (the context orchestrator path) will see the most-recently-saved ArtifactManager artifact, which may NOT be the same content as the most-recently-saved ArtifactStore artifact.

There is no `valid_until`, `superseded_by`, `requirements_version`, or `sprint_context` field on either `ArchitectureArtifact` (`shared/models/architecture_artifact.py`) or `StageArtifact` (`shared/models/stage_artifact.py`).

**Evidence:**

- `artifact/manager.py` lines 89–116: `save_artifact()` writes `artifacts/{stage.value}.json` (flat overwrite).
- `artifact/manager.py` lines 160–180: `get_artifact()` reads `artifacts/{stage.value}.json` — always "latest saved by ArtifactManager."
- `agents/architect.py` lines 96–108: `update_architecture()` calls `store.write("project", "architecture", ..., version=True)` — writing to `artifacts/project/architecture_vN.json`.
- These two paths never cross-reference or reconcile.
- `shared/models/architecture_artifact.py` lines 9–21: `ArchitectureArtifact` has a `version: int` field but no `valid_from`, `valid_until`, `superseded_at`, or `requirements_hash`.

**Impact:** After Sprint 2 adds a new technology, the Architect's `update_architecture()` creates `architecture_v2.json` in the ArtifactStore path. But the `ArtifactManager`'s `Architect.json` (which `ContextOrchestrator` reads) still contains Sprint 1's architecture unless `ArtifactManager.save_artifact()` is also called for the same content. An agent receiving the ArtifactManager version may act on stale architectural guidance.

---

## ArtifactStore Versioning Usage

**Finding:** `ArtifactStore.write(version=True)` is called ONLY during QA-triggered bug-fix updates — for `user_stories` (spec bugs) and `architecture` (architecture bugs). The initial creation of all other artifacts uses `version=False` (the default). This means the versioning mechanism exists but is only triggered reactively, not proactively.

**Evidence:**

- `agents/product_owner.py` line 97: `store.write("project", "user_stories", updated_stories, version=True)` — only called from `update_user_stories()`, which is called during bug-fix routing.
- `agents/architect.py` line 98: `store.write("project", "architecture", updated_arch, version=True)` — only called from `update_architecture()`, same bug-fix path.
- No callers of `ArtifactStore.write(version=True)` exist for any other artifact type (sprint plan, clarification, design, security, etc.).

**An agent loading an artifact cannot determine whether it is current:** `ArtifactStore.read()` returns the highest-versioned file, but returns only the data content — no metadata indicating when it was written, which sprint created it, or whether a subsequent requirement change invalidated it.

---

## Sprint Plan Staleness Detection

**Finding:** The sprint plan stored in `project.json` under `sprint_plan` is NEVER invalidated when requirements change. `ChangeManager.apply()` removes stages from `stages_completed` to trigger re-execution, but does not set `sprint_plan = None`, add a `sprint_plan.invalidated_at` timestamp, or update `sprint_plan.requirements_version`.

**Evidence:**

- `workflow/change_manager.py` lines 142–147: `apply()` updates `stages_completed`, `pending_change`, `requirement_changes`, and `current_stage`. It does NOT touch `sprint_plan`.
- `workspace/manager.py` lines 256–271: `get_sprint_plan()` deserializes `project.json["sprint_plan"]` with no staleness check.
- `shared/models/sprint.py` lines 36–56: `SprintPlan` has `created_at` and `rationale` but no `requirements_version`, `invalidated_at`, `based_on_change_id`, or `stale` flag.

**Impact:** A sprint plan created in Sprint 1 continues to be returned by `get_sprint_plan()` even after a requirement change that should replan sprints 3–5. An agent receiving the sprint plan has no mechanism to detect the staleness gap.

---

## Contradiction Detection

**Finding:** There is NO mechanism for agents to detect contradictions between old and new requirements. `ContextOrchestrator.build()` injects the last 3 requirement change descriptions as plain strings in the `requirement_changes` section of the context package. This provides narrative context but does not:
- Flag which prior artifacts are now inconsistent.
- Mark architecture or user_stories artifacts as "pre-change" vs. "post-change."
- Prevent old Sprint 1 artifacts from being injected alongside Sprint 3 context.

**Evidence:**

- `intelligence/context_orchestrator.py` lines 146–154: Loads `requirement_changes[-3:]` and adds them to `package.requirement_changes` as raw description strings.
- `intelligence/context_orchestrator.py` lines 229–258: `_load_stage_artifacts()` loads prerequisites via `ArtifactManager.get_artifact()`, which returns the latest saved flat-file artifact regardless of sprint context.
- `workflow/context_assembler.py` lines 105–116: The `_assemble_via_orchestrator` path passes ALL artifacts to the agent — architecture from Sprint 1 + requirement changes from Sprint 3 — with no contradiction signal.

---

## Context Contamination Risk

**Finding:** HIGH RISK. When `ContextOrchestrator` assembles context for a Sprint 3 agent, it loads ALL prerequisite stage artifacts from `ArtifactManager.get_artifact()` without sprint-scoping. A Sprint 3 `BackendDeveloper` receives: architecture from Sprint 1, user_stories from Sprint 1 (unless `update_user_stories` was called), AND requirement change descriptions as loose strings. There is no stamp on any artifact indicating which sprint or requirements version it reflects.

**Evidence:**

- `intelligence/context_orchestrator.py` lines 15–34 (`_STAGE_NEEDS`): `BackendDeveloper` receives `["architect", "security", "file_planner"]` artifacts — these are always the latest saves, with no sprint filter.
- `intelligence/context_orchestrator.py` lines 229–258: Artifacts are truncated at 2000 chars but otherwise injected wholesale.
- `memory/orchestrator.py` lines 60–65: `MemoryOrchestrator.get_context()` loads `clarification`, `strategic_brief`, `domain_research`, `design_artifact`, `architecture_artifact` — ALL from their respective flat `.json` files, one per stage, with no version check.
- `shared/dto/stage_context.py` lines 33–45: `StageContext` has single fields `clarification`, `architecture_artifact`, etc. — no version metadata, no sprint tag, no `is_stale` flag.

A stale Sprint 1 architecture can and will contaminate Sprint 3 context if `ArchitectAgent.update_architecture()` has not been called through the bug-fix path, or if the ArtifactManager file was not refreshed.

---

## Core Question Answer

**Can a newly-started agent reliably determine the CURRENT authoritative project requirements?**

**Answer: NO**

**Evidence Summary:**

1. `original_request` in `project.json` is never updated after a requirement change — it stays as the Sprint 1 brief.
2. `requirement_changes` is a description-only log (last 3 injected into context), not a structured delta. There is no "current requirement" field.
3. The architecture and user_stories artifacts are versioned only on the `ArtifactStore` path (in `artifacts/project/`), but `ArtifactManager.get_artifact()` reads the flat `artifacts/{stage}.json` file on a different path — these two can diverge silently.
4. The sprint plan is never invalidated when requirements change.
5. `StageContext` and `ContextPackage` contain no version stamps, sprint tags, or "valid as of" metadata on any artifact.

**Specific Failure Modes:**

1. **Stale original_request:** An agent reading `original_request` from project.json after a mid-project requirement change sees the original Sprint 1 brief, not the amended requirement.
2. **Requirement change history is description-only:** The agent sees only prose change descriptions (up to 3 in context), not structured before/after requirement diffs. It cannot determine which stories or constraints were superseded.
3. **Dual persistence path divergence:** Architecture artifacts written by `ArchitectAgent.update_architecture()` (ArtifactStore path, `artifacts/project/architecture_v2.json`) are never reflected in the ArtifactManager path (`artifacts/Architect.json`). The context orchestrator reads the ArtifactManager path and can serve a Sprint 1 architecture to a Sprint 3 agent even after a post-Sprint-1 architecture update.
4. **Sprint plan not invalidated:** A stale sprint plan (created before requirements changed) is served as-is from `project.json`. An agent cannot detect that the plan was created against different requirements.
5. **No artifact version stamps in context:** `StageContext` and `ContextPackage` carry no metadata indicating sprint number, requirements hash, or creation timestamp on any artifact. An agent cannot compare artifact ages to determine whether a loaded artifact predates or postdates a requirement change.
6. **Context orchestrator injects all prerequisite artifacts regardless of staleness:** `_load_stage_artifacts()` loads architecture, security, and planner artifacts for Sprint N without checking whether those artifacts were created before or after the last `requirement_changes` entry.
7. **ChangeManager.apply() does not update `original_request`:** The most natural place to update the canonical requirement (the `original_request` field) is left untouched during a confirmed requirement change.

---

## Minimum Model Required

The following data model would be necessary to achieve requirement authority without implementing it:

**1. `RequirementVersion` record:**  
Fields: `version_id`, `project_id`, `version_number`, `full_requirement_text` (the complete current requirements, not just a delta), `created_at`, `previous_version_id` (linked list), `change_summary`, `approved_by`, `affects_sprints` (list of sprint numbers).

**2. `current_requirement_version_id` in `project.json`:**  
A pointer from the project record to the authoritative current `RequirementVersion`. Updated atomically when a requirement change is applied.

**3. `requirements_version_id` stamp on every artifact:**  
Every `StageArtifact`, `SprintPlan`, and sprint-scoped artifact should carry the `requirement_version_id` that was current when the artifact was created. This allows any consumer to compare the artifact's version against the current version and detect staleness.

**4. `SprintPlan.requirements_version_id`:**  
The sprint plan must record which requirement version it was planned against. `ChangeManager.apply()` must set `sprint_plan.stale = True` when the new change affects planned sprints.

**5. Unified artifact persistence path:**  
`ArtifactManager` and `ArtifactStore` must be consolidated (or bridged) so that a `version=True` write in `ArtifactStore` also refreshes the `ArtifactManager` canonical file. Currently they are completely separate, creating the dual-path divergence failure mode.

**6. `ContextPackage.artifact_versions` metadata:**  
Every artifact injected into agent context must carry its `requirements_version_id` and `created_at` so the agent (or a pre-injection validator) can detect that architecture from Sprint 1 is being injected alongside Sprint 3 requirements.

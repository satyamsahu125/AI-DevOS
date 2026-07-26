# AI DevOS — Prioritized Task Backlog

**Generated**: 2026-07-27
**Source**: Audit findings from AUDIT_REPORT.md + AUDIT_FINAL_FINDINGS.md
**Priority key**: P0=blocker, P1=high, P2=medium, P3=low

---

## P0 — Blockers (fix before next dev session)

### TASK-001: Add `transformers` to requirements.txt
**Category**: Dependencies / Test Infrastructure
**Priority**: P0
**Status**: OPEN

**Description**:
`sentence-transformers` has a runtime dependency on the `transformers` package (HuggingFace).
This package is not listed in requirements.txt. Any code path that touches KnowledgeMemory's
embedding functionality fails with `ModuleNotFoundError: No module named 'transformers'`.

**Evidence**:
- test_designer_agent.py::test_reviewer_approves_well_formed_design — FAILS
- test_v1_pipeline_fixes.py::test_pattern_search_is_isolated_per_project — FAILS
- Error: `from transformers.configuration_utils import PretrainedConfig`

**Acceptance Criteria**:
- [ ] `transformers>=4.0.0` added to backend/requirements.txt
- [ ] `pip install -r requirements.txt` installs without error
- [ ] Both failing tests now pass

**Effort**: 5 minutes

---

### TASK-002: Fix stale test Fix009ScrumMasterInjection
**Category**: Test Maintenance
**Priority**: P0
**Status**: OPEN

**Description**:
Two tests in test_review_report_fixes.py create `WorkflowManager()` without `sprint_monitor`
kwarg, then call `wm._build_sprint_context()`. The method accesses `self.sprint_monitor`,
which was added in a later refactor. WorkflowManager.__init__ already accepts sprint_monitor=None
as a kwarg; tests are just constructing the object incorrectly.

**Evidence**:
```
AttributeError: 'WorkflowManager' object has no attribute 'sprint_monitor'
app/workflow/manager.py:652: in _build_sprint_context
```

**Acceptance Criteria**:
- [ ] Fix009ScrumMasterInjection.test_missing_scrum_artifact_does_not_crash passes
- [ ] Fix009ScrumMasterInjection.test_scrum_artifact_included_in_context passes

**Effort**: 30 minutes

---

### TASK-003: Fix stale test test_pipeline_runs_every_stage_in_order
**Category**: Test Maintenance
**Priority**: P0
**Status**: OPEN

**Description**:
test_v1_pipeline_fixes.py::Fix002MultiStagePipelineTests::test_pipeline_runs_every_stage_in_order
expects `FileStructurePlanner` to appear in the global stages_completed list. The code was
intentionally refactored: FileStructurePlanner now runs inside each sprint loop (not globally
before sprint planning begins). Test reflects the old design.

**Evidence**:
```
AssertionError: Lists differ: ['Str...r', 'BackendDeveloper', 'FrontendDeveloper', ...] !=
  ['Str...r', 'FileStructurePlanner', 'BackendDeveloper'...]
```

**Acceptance Criteria**:
- [ ] Test updated to reflect current stage order
- [ ] test_pipeline_runs_every_stage_in_order passes

**Effort**: 30 minutes

---

## P1 — High Priority

### TASK-004: Fix MemoryOrchestrator name collision and re-enable
**Category**: Bug Fix / Architecture
**Priority**: P1
**Status**: OPEN

**Description**:
MemoryOrchestrator has a `self.store` that is both an attribute (MemoryStore instance) and
a method (store() call). This causes attribute/method conflicts. The component is currently
commented out in container.py with the note "internal name collision". Fix the naming and
re-wire it.

**Evidence**: container.py comment: "self.store is both an attribute and a method"

**Acceptance Criteria**:
- [ ] Name collision resolved (rename attribute to self._store or self.memory_store)
- [ ] MemoryOrchestrator re-registered in container.py
- [ ] Tests pass with MemoryOrchestrator active

**Effort**: 1-2 hours

---

### TASK-005: Move hardcoded DB paths to Settings
**Category**: Configuration
**Priority**: P1
**Status**: OPEN

**Description**:
Two DB paths are hardcoded in container.py:
- `FileIndexer(db_path="backend/app/memory/file_index.db")`
- `CostTracker("backend/app/memory/costs.db")`

These cannot be overridden via config or environment. The Settings model should expose them.

**Acceptance Criteria**:
- [ ] `file_index_db` field added to Settings (config/models.py)
- [ ] `costs_db` field added to Settings
- [ ] Both added to .env.example with default values
- [ ] container.py reads from settings.file_index_db and settings.costs_db
- [ ] Existing functionality unchanged

**Effort**: 1 hour

---

### TASK-006: Set up frontend test infrastructure
**Category**: Testing
**Priority**: P1
**Status**: OPEN

**Description**:
The frontend has zero test files. No test runner (Jest/Vitest) is configured. This is a gap
flagged by multiple audits. Minimum viable test suite: render tests for ProjectsPage and
WorkspacePage, and a few unit tests for lib/api.ts.

**Acceptance Criteria**:
- [ ] Vitest + @testing-library/react configured in package.json
- [ ] At least 5 frontend tests written and passing
- [ ] `npm test` command works
- [ ] Tests cover: ProjectsPage renders project list, WorkspacePage renders without crash, api.ts error handling

**Effort**: 3-4 hours

---

### TASK-007: Write test_agents_complete.py — full agent test suite
**Category**: Testing
**Priority**: P1
**Status**: OPEN (pending from task #30 in task list)

**Description**:
A comprehensive agent test suite covering all 15 agents. Each agent should have at least:
- Construction test (agent creates without error)
- Schema validation test (agent output matches expected schema)
- Rejection handling test (agent handles reviewer rejection gracefully)

**Acceptance Criteria**:
- [ ] test_agents_complete.py created in backend/tests/
- [ ] All 15 registered agents tested
- [ ] Tests pass with mock LLM (no real Ollama required)
- [ ] At least 45 test cases (3 per agent)

**Effort**: 3-4 hours

---

## P2 — Medium Priority

### TASK-008: Wire ContextManager into live pipeline
**Category**: Architecture
**Priority**: P2
**Status**: OPEN

**Description**:
ContextManager (app/context/context.py) is implemented but disabled in container.py with the
comment "not called anywhere in the live pipeline." The original intent was for WorkflowEngine
to use it for context building instead of calling _with_predecessor_message/_with_relevant_patterns
directly. Evaluate whether to wire it in or remove it.

**Acceptance Criteria**:
- [ ] Decision documented in DECISIONS.md
- [ ] Either: ContextManager wired into WorkflowEngine + tests added
- [ ] Or: ContextManager removed from codebase + container.py cleaned up

**Effort**: 2-3 hours

---

### TASK-009: Document AWAITING_HUMAN_APPROVAL state
**Category**: Documentation / Architecture
**Priority**: P2
**Status**: OPEN

**Description**:
ProjectState.AWAITING_HUMAN_APPROVAL is in the enum but not handled in WorkflowManager.run().
Any project landing in this state hits the "unhandled state" catch block and logs an error.
IMPACT_ANALYZED and REPLANNING states have the same issue.

**Acceptance Criteria**:
- [ ] DECISIONS.md entry: what these states are for and current plan
- [ ] Either: states wired into a valid transition path
- [ ] Or: states removed from enum (if abandoned)
- [ ] WorkflowManager.run() unhandled-state catch block documents which states are intentionally unhandled

**Effort**: 1-2 hours

---

### TASK-010: Verify and fix silent exception swallowing (C1 from prior audit)
**Category**: Reliability
**Priority**: P2
**Status**: UNKNOWN

**Description**:
2026-07-25 audit found 4 files with bare `except Exception: pass` patterns:
- backend/app/api/workflow.py:122-123
- backend/app/prompt/documentation_builder.py:131
- backend/app/execution/project_reader.py:129
- backend/app/workspace/manager.py:219

These were flagged as CRITICAL. Status in current codebase is unverified. Need to check and fix.

**Acceptance Criteria**:
- [ ] Each of the 4 files verified against current source
- [ ] Any remaining bare `except: pass` patterns replaced with logged handling
- [ ] No production failures silently swallowed

**Effort**: 2-3 hours

---

### TASK-011: Add E2E / integration test
**Category**: Testing
**Priority**: P2
**Status**: OPEN

**Description**:
No end-to-end test exists that runs the full pipeline (even with mocked LLM). A single
integration test that runs a 2-stage pipeline (e.g., StrategicReview + ProductOwner) with
a mock LLM would catch wiring regressions.

**Acceptance Criteria**:
- [ ] test_pipeline_integration.py created
- [ ] Runs at least 2 pipeline stages end-to-end with mock LLM
- [ ] Verifies ProjectState transitions
- [ ] Verifies artifacts created on disk

**Effort**: 2-3 hours

---

## P3 — Low Priority

### TASK-012: Pin dependency versions in generated projects
**Category**: Code Quality
**Priority**: P3
**Status**: OPEN

**Description**:
workspace/dependency_detector.py:212 has `# TODO: pin version` when generating requirements.txt
for generated projects. Auto-detected packages get unpinned entries, which is fragile.

**Acceptance Criteria**:
- [ ] DependencyDetector resolves actual installed versions or uses safe minimum pins
- [ ] Generated requirements.txt has pinned versions for all detected packages
- [ ] TODO comment removed

**Effort**: 2-3 hours

---

### TASK-013: Verify database files not tracked in git
**Category**: Security / Repository hygiene
**Priority**: P3
**Status**: UNKNOWN (not verified in this audit)

**Description**:
2026-07-25 audit flagged SQLite .db files potentially tracked in git as CRITICAL.
Current status not verified in this audit pass.

**Acceptance Criteria**:
- [ ] `git ls-files *.db` returns empty
- [ ] .gitignore covers *.db, backend/app/memory/*.db, temp-workspace/

**Effort**: 30 minutes

---

### TASK-014: Remove or fix httpx2 deprecation warning
**Category**: Dependency hygiene
**Priority**: P3
**Status**: OPEN

**Description**:
Every pytest run shows:
`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

**Acceptance Criteria**:
- [ ] Warning resolved (upgrade httpx to httpx2, or pin to non-deprecated version)
- [ ] pytest runs without the warning

**Effort**: 30 minutes

---

## Backlog Summary

| Priority | Count | Open |
|---------|-------|------|
| P0 — Blocker | 3 | 3 |
| P1 — High | 4 | 4 |
| P2 — Medium | 4 | 4 |
| P3 — Low | 3 | 3 |
| **Total** | **14** | **14** |

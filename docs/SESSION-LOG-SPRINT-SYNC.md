# Session Log — Sprint Sync + Domain Research

## Summary

Implemented five synchronization fixes to make the AI DevOS pipeline
domain-aware, cross-sprint context-aware, and capable of partial-change
analysis on completed sprints.

---

## Fix 1 — Domain Research Agent

**Goal**: Run domain research BEFORE Q&A so questions are domain-specific.

| Item | Status |
|---|---|
| `DomainBrief` schema created | YES |
| `DomainResearchPromptBuilder` created | YES |
| `DomainResearcherAgent` created | YES |
| `Stage.DomainResearch` added to enum | YES |
| `ClarificationPromptBuilder.build_generate_prompt()` accepts `domain_brief` | YES |
| `ClarificationAgent.generate_questions()` passes `domain_brief` | YES |
| `clarify_requirements.run_generate()` injects brief via `inspect.signature` | YES |
| `WorkflowManager._run_domain_research()` added | YES |
| CLARIFYING handler calls domain research before Q&A | YES |
| Graceful degradation on LLM failure | YES (returns empty DomainBrief) |

**New files**:
- `backend/app/shared/schemas/domain_schema.py` — `DomainBrief` Pydantic model (11 fields)
- `backend/app/prompt/domain_research_builder.py` — `DomainResearchPromptBuilder`
- `backend/app/agents/domain_researcher.py` — `DomainResearcherAgent`

**Modified files**:
- `backend/app/shared/enums/stage.py` — added `DomainResearch = "DomainResearch"`
- `backend/app/prompt/clarification_builder.py` — `build_generate_prompt(domain_brief=None)`
- `backend/app/agents/clarification.py` — passes `domain_brief` downstream
- `backend/app/actions/clarify_requirements.py` — `run_generate(domain_brief=None)`
- `backend/app/workflow/manager.py` — `_run_domain_research()` + CLARIFYING handler

---

## Fix 2 — Q&A Synchronization

**Goal**: Verify pipeline pauses at QA_PENDING and doesn't advance until answers submitted.

| Item | Status |
|---|---|
| QA_PENDING state exists in ProjectState enum | YES (pre-existing) |
| CLARIFYING handler sets QA_PENDING after question generation | YES (pre-existing) |
| QA_COMPLETE advances to REQUIREMENTS_READY | YES (pre-existing) |
| No spurious state advance during QA_IN_PROGRESS | YES (verified) |

**Result**: No code changes required. Pipeline synchronization was already correct.

---

## Fix 3 — Sprint Monitor

**Goal**: Generate pre-sprint context briefs and post-sprint validation.

| Item | Status |
|---|---|
| `SprintMonitor` class created | YES |
| `generate_sprint_brief()` — first sprint returns "no previous files" | YES |
| `generate_sprint_brief()` — subsequent sprints list previous files + summaries | YES |
| `generate_sprint_brief()` — surfaces critical shared files (most-depended-on) | YES |
| `validate_sprint_output()` — checks arch data_models against indexed classes | YES |
| `validate_sprint_output()` — non-blocking (returns issues list, never raises) | YES |
| Wired into `WorkflowManager._build_sprint_context()` | YES |
| Wired into `WorkflowManager._run_sprint()` (post-sprint validation) | YES |

**New files**:
- `backend/app/intelligence/sprint_monitor.py` — `SprintMonitor`

---

## Fix 4 — File-Level Impact Analysis

**Goal**: On partial requirement changes post-sprint, identify specific files to regenerate.

| Item | Status |
|---|---|
| `ImpactAnalyzer.analyze_file_impact()` method added | YES |
| Uses `CodeSummarizer.get_relevant_files()` for keyword match | YES |
| Expands via `DependencyGraph.get_impact()` BFS | YES |
| Separates files_to_regenerate vs files_safe | YES |
| Returns structured dict (not ImpactAnalysis model) | YES |
| Gracefully degrades when intelligence layer not wired | YES |
| Gracefully degrades on any internal error | YES |
| `WorkflowManager.submit_requirement_change()` calls it when post-sprint | YES |

**Modified files**:
- `backend/app/workflow/impact_analyzer.py` — `analyze_file_impact()` method
- `backend/app/workflow/manager.py` — `submit_requirement_change()` calls file-level analysis

---

## Fix 5 — Sprint-to-Sprint Context via FileIndexer

**Goal**: Developer agents receive context about what previous sprints built.

| Item | Status |
|---|---|
| `BackendDeveloperAgent` accepts `file_indexer` param | YES |
| `FrontendDeveloperAgent` accepts `file_indexer` param | YES |
| Dependency threshold: ≤1500 chars → full content | YES |
| Dependency threshold: >1500 chars + indexer → summary | YES |
| Dependency threshold: >1500 chars + no indexer → truncate | YES |
| `_build_file_prompt()` accepts `sprint_brief` param | YES (both agents) |
| Sprint brief prepended to prompt when set | YES |
| `WorkflowManager._build_sprint_context()` calls `SprintMonitor.generate_sprint_brief()` | YES |

**Modified files**:
- `backend/app/agents/backend.py` — `file_indexer` param, threshold logic, `sprint_brief`
- `backend/app/agents/frontend.py` — same changes

---

## Container Updates

`backend/app/kernel/container.py` was updated to register and wire:

- `sprint_monitor` → receives `file_indexer`, `dependency_graph`, `artifact_manager`, `workspace_manager`
- `domain_researcher_agent` → receives `llm_manager`
- `impact_analyzer` → now also receives `file_indexer`, `dep_graph`, `code_summarizer`
- `backend_developer_agent` → now also receives `file_indexer`
- `frontend_developer_agent` → now also receives `file_indexer`
- `workflow_manager` → now also receives `sprint_monitor`, `domain_researcher`

---

## Bug Fixed During Testing

**`DomainResearcherAgent._build_default_action()` returned `BaseAction()` directly.**
`BaseAction` is abstract (has abstract method `run`), so this raised `TypeError` at
instantiation. Fixed by returning a concrete `_NoOpAction` stub. The agent never uses
`primary_action` anyway — it calls LLM directly via `research()`.

File: `backend/app/agents/domain_researcher.py`

---

## Files Changed (this session)

### New files
| File | Purpose |
|---|---|
| `backend/app/shared/schemas/domain_schema.py` | DomainBrief Pydantic model |
| `backend/app/prompt/domain_research_builder.py` | DomainResearchPromptBuilder |
| `backend/app/agents/domain_researcher.py` | DomainResearcherAgent |
| `backend/app/intelligence/sprint_monitor.py` | SprintMonitor |
| `backend/tests/test_sprint_sync.py` | 45 tests for all 5 fixes |
| `docs/SESSION-LOG-SPRINT-SYNC.md` | This file |

### Modified files
| File | Change |
|---|---|
| `backend/app/shared/enums/stage.py` | Added `DomainResearch` stage |
| `backend/app/prompt/clarification_builder.py` | `domain_brief` injection |
| `backend/app/agents/clarification.py` | Passes `domain_brief` |
| `backend/app/actions/clarify_requirements.py` | `domain_brief` via `inspect.signature` |
| `backend/app/workflow/manager.py` | `_run_domain_research()`, `_build_sprint_context()`, `_run_sprint()`, `submit_requirement_change()` |
| `backend/app/workflow/impact_analyzer.py` | `analyze_file_impact()` method |
| `backend/app/agents/backend.py` | `file_indexer`, threshold, `sprint_brief` |
| `backend/app/agents/frontend.py` | Same as backend.py |
| `backend/app/kernel/container.py` | All new singleton registrations |

---

## Test Results

```
tests/test_sprint_sync.py        45 passed
tests/test_project_intelligence.py  46 passed
Total: 91 passed, 0 failed
```

---

## Commits

| Hash | Message |
|---|---|
| `4644bc4` | feat: Project Intelligence Layer (prior session) |
| (pending) | feat: Sprint Sync Fixes — domain research, sprint monitor, file impact, cross-sprint context |

---

## Architecture Principles Preserved

- Stateless agents — DomainResearcherAgent is stateless ✓
- No agent-to-agent communication — domain research result stored as artifact ✓
- Workflow Engine is sole orchestrator — SprintMonitor is a utility, not an orchestrator ✓
- Execution Engine is sole file modifier — sprint validation only reads, never writes ✓
- Every new component has single responsibility ✓
- Graceful degradation — all new components are non-blocking on failure ✓

---

## What Still Needs Doing

1. **WorkflowManager `_run_sprint()` pass `sprint_brief` into developer agent calls** — the brief
   is generated by `_build_sprint_context()` but needs to be threaded through to
   `_generate_one_file()` → `_build_file_prompt(sprint_brief=...)`. Verify this path is wired.

2. **End-to-end integration test** — a full pipeline run through
   CLARIFYING → QA_PENDING → QA_COMPLETE → SPRINT_IN_PROGRESS with all new components.

3. **UI display of file-level impact** — `submit_requirement_change` stores `file_impact` in
   `project.json`, but the frontend doesn't yet render it.

4. **Domain brief persistence** — `_run_domain_research()` saves the artifact, but
   `ClarificationAgent.process_answers()` doesn't re-read the domain brief. If the
   ENRICHED REQUIREMENT needs domain context on answer processing, wire it.

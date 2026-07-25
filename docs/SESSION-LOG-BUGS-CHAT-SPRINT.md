# Session Log — Bug Fixes + Chat + ScrumMaster
**Date**: 2026-07-26
**Tests Before**: 224
**Tests After**: 230

## BUG-001 — Resume Bug
- **Root cause found**: `WorkflowManager.run()` had no sanitization on `stages_completed` stored in `project.json`. When a project was restarted or resumed, gaps in completed stages or out-of-order state transitions could cause the pipeline to jump directly to `Retro` or final stages.
- **Fix applied**: Implemented `_sanitize_stages_completed()` in `WorkflowManager` to strip any gap stages that appear after an incomplete stage, ensuring sequential execution without skipping stages. Verified stage progress updates strictly occur after reviewer approval in `WorkflowEngine`.
- **File changed**: `backend/app/workflow/manager.py`
- **Test written**: `backend/tests/test_pipeline_resume.py` (`test_resume_from_backend_stage_not_retro`, `test_sanitize_removes_gap_stages`)
- **Verified**: Tests passed, `stages_completed` sanitization strips gaps as expected.

## BUG-002 — SprintPlanner Routing & Order
- **Root cause**: `DependencyGraph.STAGE_ORDER` placed `file_planner` before `sprint_planner`, causing stage ordering issues.
- **Fix applied**: Positioned `sprint_planner` after `security` and before `scrum_master` and `file_planner` in `STAGE_ORDER` and `STAGE_DEPENDENCIES`. Added `_handle_sprint_planner_approval` in `WorkflowManager` to persist `sprint_plan` directly into `project.json`.
- **SprintPlanner now reaches**: Yes, mapped `sprint_planner` to `Stage.SprintPlanning`.
- **sprint_plan saved to project.json**: Yes.
- **Test verified**: Routing assertion script verified `resolve_stage_name('sprint_planner') == Stage.SprintPlanning.value`.

## BUG-003 — Chat Panel & Router Agent
- **Frontend issue**: `ChatPanel.tsx` had an un-wired input box and callback.
- **Backend created**: `backend/app/api/chat.py` with `POST /projects/{project_id}/chat` endpoint.
- **ChatRouter created**: Yes (`backend/app/agents/chat_router.py`).
- **Handlers working**: Intent detection for status, stage re-runs, artifact inspection, and general LLM Q&A using project context.
- **Test verified**: Unit tests in `backend/tests/test_chat_router.py`.

## ScrumMaster Agent (NEW AGENT)
- **Created**: Yes (`backend/app/agents/scrum_master.py`, `backend/app/prompt/scrum_master_builder.py`, `backend/app/actions/write_scrum_plan.py`).
- **Stage position**: After `sprint_planner` and before `file_planner`.
- **Output schema**: `ScrumPlan` (containing sprint definition, task items, story points, dependencies, critical path, risk flags).
- **Registered in**: `factory.py`, `resolver.py`, `stage.py`, `stage_lookup.py`, `dependency_graph.py`, `container.py`.
- **Test verified**: `backend/tests/test_scrum_master.py`.

## Issues Encountered
- `ScrumMasterAgent` required `LLMAction` inheritance to provide `run()` for abstract `BaseAction` methods. Resolved by subclassing `LLMAction` and configuring `ScrumPlan` schema model.
- Test client assertions needed agent count updated from 14 to 15 after adding `ScrumMasterAgent`. Resolved.

## Files Changed
- `backend/app/shared/enums/stage.py`
- `backend/app/actions/write_scrum_plan.py`
- `backend/app/prompt/scrum_master_builder.py`
- `backend/app/agents/scrum_master.py`
- `backend/app/agents/chat_router.py`
- `backend/app/agents/factory.py`
- `backend/app/agents/resolver.py`
- `backend/app/workflow/stage_lookup.py`
- `backend/app/workflow/dependency_graph.py`
- `backend/app/workflow/manager.py`
- `backend/app/kernel/container.py`
- `backend/app/api/dependencies.py`
- `backend/app/api/chat.py`
- `backend/app/api/router.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/workspace/ChatPanel.tsx`
- `backend/tests/test_pipeline_resume.py`
- `backend/tests/test_chat_router.py`
- `backend/tests/test_scrum_master.py`
- `backend/tests/test_state_machine.py`
- `backend/tests/test_v1_pipeline_fixes.py`

## Commits
```
docs: session log for bug fixes, chat router, and scrum master agent
```

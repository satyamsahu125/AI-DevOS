Track 2 Phase 3 is complete. This is the final prompt — Phase 4: cut over to the event log as source of truth, remove dead files, and lock in a CI smoke gate. After this, the full Track 2 migration is done.

---

FIX 19 — Cut workflow.json reads over to EventStore

Phase 3 added dual-write (events + workflow.json). Now switch all reads to use EventStore.replay_state() instead of reading workflow.json.

Find every place in the codebase that reads workflow.json to get current workflow state — look for open(), json.load(), or any file read that references "workflow.json" or loads workflow state from disk.

For each read site, replace it with:

  from app.workflow.event_store import EventStore
  store = EventStore(db)
  state = store.replay_state(workflow_id)

The replay_state() method already returns a dict compatible with the existing state shape — that was the design in Phase 3.

Keep the workflow.json write path in place for now as a backup. Do not remove it yet. Only remove the read path.

After this change, if any code path falls through to workflow.json as a fallback when EventStore returns an empty dict (no events yet for a workflow_id), that fallback is acceptable during the transition. Add a log warning when the fallback fires:
  logger.warning("workflow_id %s not in event store, falling back to workflow.json", workflow_id)

---

FIX 20 — Delete dead files from the repository

Run these exact git rm commands. Do not delete anything not listed here.

Root level:
  git rm direct_run.log
  git rm direct_run_report.json
  git rm task1.txt.txt
  git rm fix1.md
  git rm AUDIT_REPORT.md
  git rm ARCHITECTURE_VALIDATION.md
  git rm DESIGN_SPEC.md
  git rm FINAL_REVIEW.md
  git rm VALIDATION_GATES.md
  git rm TEST_STRATEGY.md
  git rm FRONTEND_MIGRATION_PLAN.md
  git rm DISCOVERY_NOTES.md
  git rm CODEBASE_MAP.md
  git rm FIX_LOG.md
  git rm ai_devos_opencode.md

Backend:
  git rm backend/test_results.txt
  git rm -r backend/_stale_backend_to_delete/
  git rm backend/app/memory/AUDIT_FINDINGS.md

If any file in this list does not exist (already deleted), skip it — do not error out. Use git rm --ignore-unmatch for safety:
  git rm --ignore-unmatch direct_run.log direct_run_report.json task1.txt.txt fix1.md AUDIT_REPORT.md ARCHITECTURE_VALIDATION.md DESIGN_SPEC.md FINAL_REVIEW.md VALIDATION_GATES.md TEST_STRATEGY.md FRONTEND_MIGRATION_PLAN.md DISCOVERY_NOTES.md CODEBASE_MAP.md FIX_LOG.md ai_devos_opencode.md
  git rm --ignore-unmatch backend/test_results.txt backend/app/memory/AUDIT_FINDINGS.md
  git rm -r --ignore-unmatch backend/_stale_backend_to_delete/

---

FIX 21 — Add CI smoke test gate

Create backend/tests/test_smoke_imports.py:

  """
  Smoke tests — verify the application can import without errors.
  These tests cost nothing to run and catch missing-file ImportErrors
  before they reach production.
  """
  import pytest

  def test_fastapi_app_imports():
      from app.api import app
      assert app is not None

  def test_workflow_engine_imports():
      from app.workflow.engine import WorkflowEngine
      assert WorkflowEngine is not None

  def test_event_store_imports():
      from app.workflow.event_store import EventStore, EventType
      assert EventStore is not None
      assert len(list(EventType)) >= 8

  def test_artifact_contracts_import():
      from app.artifacts.contracts import (
          RequirementsArtifact, ArchitectureArtifact,
          CodingArtifact, ReviewArtifact, GenericArtifact,
      )
      assert RequirementsArtifact is not None

  def test_gate_config_loads():
      from app.workflow.gate_config import GateConfigLoader
      loader = GateConfigLoader()
      gate = loader.get("requirements")
      assert gate.review_type == "human"
      gate_default = loader.get("nonexistent_stage_xyz")
      assert gate_default.review_type is not None   # defaults apply

  def test_agent_factory_imports():
      from app.agents.factory import AgentFactory
      assert AgentFactory is not None

These 6 tests must always pass. They are the minimum bar for "the system can start."

---

FIX 22 — Delete the two broken pre-existing tests

Read backend/tests/test_context_budget.py and backend/tests/test_dynamic_prompts.py.

test_context_budget.py tests a 1000-character truncation rule that no longer exists in the codebase. It will never pass against the current implementation.

test_dynamic_prompts.py references BackendPromptBuilder.SYSTEM_PROMPT which does not exist.

Delete both files:
  git rm backend/tests/test_context_budget.py
  git rm backend/tests/test_dynamic_prompts.py

Do not try to fix them. They test behaviour that was removed or never implemented. Keeping permanently failing tests in the suite creates noise that masks real failures.

---

Final validation — run this entire sequence:

  cd backend && python -m pytest tests/test_smoke_imports.py -v
  cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20

Expected outcome:
  - All 6 smoke tests pass
  - Total test count is 95 minus the 2 deleted test files worth of tests (net ~91+)
  - Zero failures

Then commit everything:
  git add -A
  git status   # review before committing — make sure no unintended files are staged
  git commit -m "Track 2 complete: event sourcing, declarative gates, persistent memory, dead code removed"

The system now has:
  - Correct state machine (Track 1)
  - Atomic concurrency guards (Track 1)
  - Redis execution state (Phase 1)
  - Pydantic artifact contracts (Phase 1)
  - Single write path for project files (Phase 1)
  - Declarative review gates via gates.yaml (Phase 2)
  - Postgres-backed memory with real cleanup (Phase 2)
  - Append-only event log as state source of truth (Phase 3 + 4)
  - CI smoke gate that catches startup failures immediately (Phase 4)
  - Clean repository with no dead log/audit files (Phase 4)
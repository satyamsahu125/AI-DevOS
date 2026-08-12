"""test_phase5_sandbox_to_buganalyst_e2e.py — Phase 5 E2E regression.

Covers the production path end-to-end:
  1. _run_sandbox() calls code_sandbox.run() → gets SandboxResult
  2. SandboxResult.to_json() is stored at memory_manager["sandbox:latest"]
  3. ContextAssembler._inject_sandbox_results() reads "sandbox:latest" and
     prepends an "AUTOMATED VERIFICATION RESULTS" header to the BugAnalyst prompt.

Does NOT redesign or refactor the path — exercises existing interfaces exactly.

Running:
    cd backend
    python -m pytest tests/test_phase5_sandbox_to_buganalyst_e2e.py -v
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# In-memory MemoryManager stand-in
# ---------------------------------------------------------------------------

class _InMemoryMemoryManager:
    """Pure-dict replacement for MemoryManager — no SQLite, no I/O.

    Exposes exactly the two methods _run_sandbox() and
    _inject_sandbox_results() depend on.
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def store(self, project_id: str, key: str, value: str) -> None:
        self._data[(project_id, key)] = value

    def load(self, project_id: str, key: str) -> str | None:
        return self._data.get((project_id, key))


# ---------------------------------------------------------------------------
# Helper: build a minimal PipelineSupervisor for _run_sandbox() testing
# ---------------------------------------------------------------------------

def _make_supervisor(memory_manager: _InMemoryMemoryManager, sandbox_result):
    """Return a PipelineSupervisor wired with mock code_sandbox and the given memory_manager."""
    from app.workflow.pipeline_supervisor import PipelineSupervisor

    # ArtifactStore: report no pre-existing sandbox result, forcing the
    # code_sandbox.run() fallback path inside _run_sandbox().
    artifact_store = MagicMock()
    artifact_store.exists.return_value = False

    workspace = MagicMock()
    workspace.get_artifact_store.return_value = artifact_store

    code_sandbox = MagicMock()
    code_sandbox.run.return_value = sandbox_result

    return PipelineSupervisor(
        workspace=workspace,
        engine=MagicMock(),
        sprint_executor=MagicMock(),
        settings=MagicMock(),
        code_sandbox=code_sandbox,
        memory_manager=memory_manager,
    )


# ---------------------------------------------------------------------------
# E2E test class
# ---------------------------------------------------------------------------

class TestSandboxToBugAnalystE2E:
    """End-to-end: _run_sandbox() writes sandbox:latest; _inject_sandbox_results() reads it."""

    PROJECT_ID = "e2e-test-proj"
    SPRINT = 1

    def setup_method(self):
        from app.shared.dto.sandbox_result import SandboxResult
        from app.workflow.context_assembler import ContextAssembler

        self._memory_manager = _InMemoryMemoryManager()
        # SandboxResult.disabled() is the lightest real SandboxResult we can build —
        # it still produces a valid JSON payload with the keys _inject_sandbox_results reads.
        self._sandbox_result = SandboxResult.disabled(self.PROJECT_ID, sprint=self.SPRINT)
        # code_sandbox.run() is called as run(project_id, sprint=sprint_number) — mock handles both
        self._supervisor = _make_supervisor(self._memory_manager, self._sandbox_result)
        self._assembler = ContextAssembler(memory_manager=self._memory_manager)

    # ── 1. _run_sandbox() stores to memory ───────────────────────────────────

    def test_run_sandbox_stores_non_none_string_to_memory(self):
        """_run_sandbox() must write a non-empty string to 'sandbox:latest'."""
        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        stored = self._memory_manager.load(self.PROJECT_ID, "sandbox:latest")
        assert stored is not None
        assert isinstance(stored, str)
        assert len(stored) > 0

    def test_stored_value_is_valid_json(self):
        """The value stored at 'sandbox:latest' must be valid, parseable JSON."""
        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        stored = self._memory_manager.load(self.PROJECT_ID, "sandbox:latest")
        parsed = json.loads(stored)
        assert isinstance(parsed, dict)

    def test_stored_json_has_lint_build_test_keys(self):
        """Stored JSON must contain the keys _inject_sandbox_results() expects."""
        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        stored = self._memory_manager.load(self.PROJECT_ID, "sandbox:latest")
        parsed = json.loads(stored)
        assert "lint" in parsed, "missing 'lint' key in stored sandbox JSON"
        assert "build" in parsed, "missing 'build' key in stored sandbox JSON"
        assert "test" in parsed, "missing 'test' key in stored sandbox JSON"

    # ── 2. _inject_sandbox_results() reads sandbox:latest and prepends header ─

    def test_inject_prepends_automated_header_before_buganalyst_prompt(self):
        """Full path: store → load → format. Header must appear before original text."""
        from app.shared.enums.stage import Stage

        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        original = "Analyse the following code for bugs."
        result = self._assembler._inject_sandbox_results(
            self.PROJECT_ID, Stage.BugAnalyst.value, original
        )
        assert "AUTOMATED VERIFICATION RESULTS" in result
        assert original in result
        # Critically: header must come BEFORE the original content
        assert result.index("AUTOMATED VERIFICATION RESULTS") < result.index(original)

    def test_inject_result_contains_lint_line(self):
        """Injected prompt must include a 'Lint errors:' line."""
        from app.shared.enums.stage import Stage

        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        result = self._assembler._inject_sandbox_results(
            self.PROJECT_ID, Stage.BugAnalyst.value, "content"
        )
        assert "Lint errors:" in result

    def test_inject_result_contains_build_line(self):
        """Injected prompt must include a 'Build:' status line."""
        from app.shared.enums.stage import Stage

        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        result = self._assembler._inject_sandbox_results(
            self.PROJECT_ID, Stage.BugAnalyst.value, "content"
        )
        assert "Build:" in result

    def test_inject_result_contains_tests_line(self):
        """Injected prompt must include a 'Tests:' pass/total line."""
        from app.shared.enums.stage import Stage

        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        result = self._assembler._inject_sandbox_results(
            self.PROJECT_ID, Stage.BugAnalyst.value, "content"
        )
        assert "Tests:" in result

    # ── 3. Stage gating — non-BugAnalyst stages pass through unchanged ────────

    def test_inject_returns_original_for_non_buganalyst_stage(self):
        """_inject_sandbox_results() must not modify prompts for other stages."""
        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        original = "CodeGenerator prompt content"
        result = self._assembler._inject_sandbox_results(
            self.PROJECT_ID, "CodeGenerator", original
        )
        assert result == original

    def test_inject_returns_original_for_empty_stage(self):
        """Edge case: empty stage name must pass through unchanged."""
        self._supervisor._run_sandbox(self.PROJECT_ID, sprint_number=self.SPRINT)
        original = "some prompt"
        result = self._assembler._inject_sandbox_results(self.PROJECT_ID, "", original)
        assert result == original

    # ── 4. Graceful degradation when sandbox:latest is absent ─────────────────

    def test_inject_degrades_gracefully_when_no_sandbox_result_stored(self):
        """If _run_sandbox() was never called, prompt must pass through unchanged."""
        from app.shared.enums.stage import Stage
        from app.workflow.context_assembler import ContextAssembler

        assembler = ContextAssembler(memory_manager=_InMemoryMemoryManager())
        original = "original prompt — no sandbox ran"
        result = assembler._inject_sandbox_results(
            "brand-new-project", Stage.BugAnalyst.value, original
        )
        assert result == original

    def test_inject_degrades_gracefully_when_memory_manager_is_none(self):
        """ContextAssembler with memory_manager=None must return prompt unchanged."""
        from app.shared.enums.stage import Stage
        from app.workflow.context_assembler import ContextAssembler

        assembler = ContextAssembler(memory_manager=None)
        original = "original prompt"
        result = assembler._inject_sandbox_results(
            self.PROJECT_ID, Stage.BugAnalyst.value, original
        )
        assert result == original

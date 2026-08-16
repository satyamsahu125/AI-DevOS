"""Tests for parallel file generation in BackendDeveloperAgent.

Verifies three core behaviours of the wave-based DAG executor
introduced by SPRINT_PARALLEL_FILES:

1. Independent files dispatch concurrently (all start within 0.5 s).
2. Dependent files wait for their prerequisites (A→B→C ordering enforced).
3. A failed file does not block sibling files with no dependency on it.

Running
-------
From the ``backend/`` directory::

    pytest tests/test_parallel_sprint.py -v

Environment variable ``SPRINT_PARALLEL_FILES`` is patched per-test via
:func:`unittest.mock.patch.dict` so the global env is never mutated.
"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.agents.backend import BackendDeveloperAgent
from app.shared.dto.sprint_execution import FileGenerationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_spec(file_path: str, depends_on: list[str] | None = None) -> SimpleNamespace:
    """Return a minimal FileSpec-compatible object for use in tests."""
    ns = SimpleNamespace()
    ns.file_path = file_path
    ns.language = "python"
    ns.depends_on = depends_on or []
    return ns


def _make_file_plan(
    files: dict,
    generation_order: list[str] | None = None,
) -> SimpleNamespace:
    """Return a minimal FilePlan-compatible object for use in tests."""
    ns = SimpleNamespace()
    ns.files = files
    ns.generation_order = generation_order if generation_order is not None else list(files.keys())
    ns.sprint_number = 1
    ns.tech_stack = None
    return ns


def _make_agent() -> BackendDeveloperAgent:
    """Return a BackendDeveloperAgent with all external deps mocked out.

    Uses ``__new__`` to bypass ``__init__`` so no real LLM / writer / validator
    dependencies need to be wired up.  Only the attributes accessed by
    ``execute_sprint`` and ``_execute_sprint_parallel`` are set.
    """
    agent = BackendDeveloperAgent.__new__(BackendDeveloperAgent)

    # Attributes checked by execute_sprint / _execute_sprint_parallel
    agent._language_profile = None
    agent._resolved_profile = None
    agent._file_indexer = None       # disables _index_file_if_available (no-op)
    agent.MAX_ATTEMPTS_PER_FILE = 3

    # Stub _resolve_language_profile so profile resolution never calls LLM
    profile = SimpleNamespace(language="python", framework="fastapi")
    agent._resolve_language_profile = MagicMock(return_value=profile)

    return agent


def _ok(file_path: str) -> FileGenerationResult:
    """Return a successful FileGenerationResult for *file_path*."""
    return FileGenerationResult(file_path=file_path, success=True, attempts=1, last_error="")


def _fail(file_path: str) -> FileGenerationResult:
    """Return a failed FileGenerationResult for *file_path*."""
    return FileGenerationResult(
        file_path=file_path, success=False, attempts=3, last_error="Simulated LLM error"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParallelFileSprint:
    """Wave-based parallel execution in BackendDeveloperAgent._execute_sprint_parallel."""

    # ------------------------------------------------------------------
    # Test 1 — independent files run concurrently
    # ------------------------------------------------------------------

    def test_independent_files_run_in_parallel(self):
        """Three files with no ``depends_on`` must all START within 0.5 s of each other.

        Each fake generation sleeps for 0.3 s.  If the files ran sequentially
        the total time would be ≥ 0.9 s and the start-time spread would be ≥ 0.6 s.
        With SPRINT_PARALLEL_FILES=3 all three should fire simultaneously and the
        spread must stay below 0.5 s.
        """
        DELAY = 0.3  # seconds each fake generation takes

        start_times: dict[str, float] = {}
        lock = threading.Lock()

        agent = _make_agent()

        path_user = "backend/app/models/user.py"
        path_product = "backend/app/models/product.py"
        path_order = "backend/app/models/order.py"

        files_map = {
            path_user: _make_file_spec(path_user),
            path_product: _make_file_spec(path_product),
            path_order: _make_file_spec(path_order),
        }
        file_plan = _make_file_plan(files_map, [path_user, path_product, path_order])

        def fake_generate(project_id, file_path, file_spec, file_plan, context, profile):
            with lock:
                start_times[file_path] = time.monotonic()
            time.sleep(DELAY)
            return _ok(file_path)

        agent._generate_one_file = fake_generate  # type: ignore[method-assign]

        with patch.dict(os.environ, {"SPRINT_PARALLEL_FILES": "3"}):
            result = agent.execute_sprint(
                project_id="proj-parallel-1", file_plan=file_plan, context=None
            )

        assert result.success, (
            f"Expected all files to succeed; failed: {[r.file_path for r in result.failed_files]}"
        )
        assert len(result.written_files) == 3, (
            f"Expected 3 written files, got {len(result.written_files)}"
        )

        assert len(start_times) == 3, f"Expected 3 start timestamps, got {start_times}"
        spread = max(start_times.values()) - min(start_times.values())
        assert spread < 0.5, (
            f"Files did not start concurrently — start-time spread was {spread:.3f} s "
            f"(threshold 0.5 s).  start_times={start_times}"
        )

    # ------------------------------------------------------------------
    # Test 2 — chained deps enforce ordering
    # ------------------------------------------------------------------

    def test_dependent_file_waits(self):
        """A → B → C chain: each file must start only after its predecessor finishes.

        Timestamps are recorded per file.  Post-run assertions verify:
        * ``A.end ≤ B.start`` — B did not start until A finished.
        * ``B.end ≤ C.start`` — C did not start until B finished.

        SPRINT_PARALLEL_FILES=3 so the executor *would* run all three
        concurrently if it ignored deps — the ordering must come from the wave
        algorithm, not from a low thread count.
        """
        DELAY = 0.05  # seconds — short to keep the test fast

        timestamps: dict[str, dict[str, float]] = {}
        lock = threading.Lock()

        agent = _make_agent()

        path_a = "backend/app/models/a.py"
        path_b = "backend/app/services/b.py"
        path_c = "backend/app/api/c.py"

        files_map = {
            path_a: _make_file_spec(path_a),
            path_b: _make_file_spec(path_b, depends_on=[path_a]),
            path_c: _make_file_spec(path_c, depends_on=[path_b]),
        }
        file_plan = _make_file_plan(files_map, [path_a, path_b, path_c])

        def fake_generate(project_id, file_path, file_spec, file_plan, context, profile):
            t0 = time.monotonic()
            time.sleep(DELAY)
            t1 = time.monotonic()
            with lock:
                timestamps[file_path] = {"start": t0, "end": t1}
            return _ok(file_path)

        agent._generate_one_file = fake_generate  # type: ignore[method-assign]

        with patch.dict(os.environ, {"SPRINT_PARALLEL_FILES": "3"}):
            result = agent.execute_sprint(
                project_id="proj-chain-2", file_plan=file_plan, context=None
            )

        assert result.success, (
            f"Expected all files to succeed; failed: {[r.file_path for r in result.failed_files]}"
        )
        assert set(timestamps.keys()) == {path_a, path_b, path_c}, (
            f"Expected timestamps for all 3 files; got {set(timestamps.keys())}"
        )

        # B must not start before A finishes
        assert timestamps[path_a]["end"] <= timestamps[path_b]["start"] + 1e-6, (
            f"B started before A finished: "
            f"A.end={timestamps[path_a]['end']:.6f}  B.start={timestamps[path_b]['start']:.6f}"
        )
        # C must not start before B finishes
        assert timestamps[path_b]["end"] <= timestamps[path_c]["start"] + 1e-6, (
            f"C started before B finished: "
            f"B.end={timestamps[path_b]['end']:.6f}  C.start={timestamps[path_c]['start']:.6f}"
        )

    # ------------------------------------------------------------------
    # Test 3 — failed file does not block unrelated files
    # ------------------------------------------------------------------

    def test_failed_file_doesnt_block_others(self):
        """File B fails; file C (no dep on B) must still be generated successfully.

        Layout::

            A ──────────── succeeds  (no deps)
            B ──────────── FAILS     (no deps)
            C ── dep: A ── succeeds  (B's failure is irrelevant)
            D ── dep: B ── orphaned  (B never completed → D never scheduled)

        Expected outcome:
        * ``result.written_files`` contains A and C.
        * ``result.failed_files`` contains B (actual failure) and D (orphaned).
        * D's ``last_error`` contains the word "Skipped".
        * Overall ``result.success`` is False (because B and D failed).
        """
        agent = _make_agent()

        path_a = "backend/app/models/a.py"
        path_b = "backend/app/models/b.py"
        path_c = "backend/app/services/c.py"   # depends on A only
        path_d = "backend/app/services/d.py"   # depends on B → will be orphaned

        files_map = {
            path_a: _make_file_spec(path_a),
            path_b: _make_file_spec(path_b),
            path_c: _make_file_spec(path_c, depends_on=[path_a]),
            path_d: _make_file_spec(path_d, depends_on=[path_b]),
        }
        file_plan = _make_file_plan(files_map, [path_a, path_b, path_c, path_d])

        def fake_generate(project_id, file_path, file_spec, file_plan, context, profile):
            if file_path == path_b:
                return _fail(file_path)
            return _ok(file_path)

        agent._generate_one_file = fake_generate  # type: ignore[method-assign]

        with patch.dict(os.environ, {"SPRINT_PARALLEL_FILES": "2"}):
            result = agent.execute_sprint(
                project_id="proj-failure-3", file_plan=file_plan, context=None
            )

        # Overall sprint must be marked failed (B and D both failed)
        assert not result.success, "Expected overall failure because B and D failed"

        written_paths = {r.file_path for r in result.written_files}
        failed_paths = {r.file_path for r in result.failed_files}

        # A and C must succeed despite B's failure
        assert path_a in written_paths, (
            f"A should have succeeded; written={written_paths}"
        )
        assert path_c in written_paths, (
            f"C should have succeeded (no dep on B); written={written_paths}"
        )

        # B must appear in failed with its original error
        assert path_b in failed_paths, (
            f"B should have failed; failed={failed_paths}"
        )

        # D must be orphaned (recorded with "Skipped" message, attempts=0)
        assert path_d in failed_paths, (
            f"D should be orphaned (dep on failed B); failed={failed_paths}"
        )
        d_result = next(r for r in result.failed_files if r.file_path == path_d)
        assert "Skipped" in (d_result.last_error or ""), (
            f"D should be orphaned with a 'Skipped' error message; "
            f"got: {d_result.last_error!r}"
        )
        assert d_result.attempts == 0, (
            f"Orphaned file D must have attempts=0 (never ran); got {d_result.attempts}"
        )

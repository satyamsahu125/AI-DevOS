"""StageRunner — single responsibility: execute → review → retry.

Knows nothing about memory assembly, checkpoints, git, learning, or progress.
Those are handled by the middleware classes that WorkflowEngine composes on top.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Maximum characters allowed in the prompt sent to the LLM.
# Bedrock Claude models have a 262 144-token context window; at ~3.5 chars/token
# that is ~917 000 chars total.  Reserving ~4 096 output tokens (14 336 chars)
# and a 20 % safety margin gives a safe input cap of ~720 000 chars.
# We use 600 000 to leave headroom for the system prompt added by the provider.
_MAX_CONTEXT_CHARS: int = 600_000

# Substrings that identify a provider context-length rejection.
# When the exception message contains any of these, the error is caused by an
# oversized prompt — not by a logic bug in the agent — and can be mitigated
# by trimming the context before the next attempt.
_CONTEXT_OVERFLOW_MARKERS: tuple[str, ...] = (
    "maximum context length",
    "input tokens",
    "context window",
    "prompt is too long",
    "reduce the length",
    "exceeds the model's maximum",
)


@dataclass
class StageRunResult:
    """Outcome of one StageRunner.run() call."""

    success: bool
    artifact: Any | None = None          # StageArtifact when success=True
    message: str = ""
    attempt_count: int = 0
    stopped: bool = False
    failed_approaches: list[str] = field(default_factory=list)
    duration_sec: float = 0.0
    review_result: Any | None = None     # final ReviewResult (approved or last rejection)


class StageRunner:
    """Runs exactly one pipeline stage through execute → review → retry.

    Parameters
    ----------
    execution_manager:
        Calls the agent for the given stage and returns an ExecutionResult.
    reviewer:
        Evaluates artifact quality; returns a ReviewResult with .approved flag.
    retry_policy:
        Decides whether another attempt is warranted (should_retry(attempt) → bool).
    event_log:
        Structured per-stage event recorder.
    broadcaster:
        WebSocket progress pusher (stage_started / stage_complete / stage_retry /
        stage_failed).
    retry_engine:
        Optional intelligent retry planner. If None, plain RetryPolicy controls
        retries.
    execution_state:
        If provided, checked for stop-requests between attempts.
    """

    def __init__(
        self,
        execution_manager: Any,
        reviewer: Any,
        retry_policy: Any,
        event_log: Any,
        broadcaster: Any,
        retry_engine: Any = None,
        execution_state: Any = None,
        artifact_manager: Any = None,
    ) -> None:
        self.execution_manager = execution_manager
        self.reviewer = reviewer
        self.retry_policy = retry_policy
        self.event_log = event_log
        self.broadcaster = broadcaster
        self.retry_engine = retry_engine
        self.execution_state = execution_state
        # Optional — when present, enables cross-stage consistency checks
        # (Architecture modules → BackendDev/FrontendDev written files, and
        # Architecture endpoints → Designer api_dependencies).
        self.artifact_manager = artifact_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        project_id: str,
        stage_name: str,
        context: str,
        on_attempt: Callable[[int, Any, Any], None] | None = None,
    ) -> StageRunResult:
        """Execute stage_name with assembled context, retrying on rejection.

        Parameters
        ----------
        project_id:
            Project being built.
        stage_name:
            Canonical stage name (e.g. "Architect", "BackendDeveloper").
        context:
            Fully assembled prompt context produced by ContextAssembler.
        on_attempt:
            Optional hook called after every attempt (approved or rejected) with
            ``(attempt_index: int, artifact: StageArtifact, review_result)``.
            Used by LearningMiddleware to record trajectories without coupling
            to StageRunner.
        """
        stage_start = datetime.now(timezone.utc)
        self.event_log.record(project_id, stage_name, f"{stage_name} started")

        attempt = 0
        review_result = None
        reviewer_feedback = ""
        failed_approaches: list[str] = []
        last_artifact_summary = ""
        last_error = ""

        # When IntelligentRetryEngine is wired in, it is the sole loop gate:
        # "while True" with the engine deciding whether to continue after each
        # rejection.  Without the engine, the legacy RetryPolicy counter governs
        # the loop — preserving pre-Phase-2 behaviour exactly.
        _engine_driven = self.retry_engine is not None

        while True:
            # ── Attempt budget check (legacy gate when no engine) ────
            if not _engine_driven and not self.retry_policy.should_retry(attempt):
                break

            # ── Stop check ───────────────────────────────────────────
            if (
                self.execution_state is not None
                and self.execution_state.is_stop_requested(project_id)
            ):
                logger.info("stage stopped by user: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(
                    project_id, stage_name,
                    f"{stage_name} stopped before attempt {attempt + 1}",
                    level="warning",
                )
                return StageRunResult(
                    success=False,
                    stopped=True,
                    message="Stopped by user",
                    attempt_count=attempt,
                    failed_approaches=failed_approaches,
                )

            logger.info("stage attempt: stage=%s attempt=%s", stage_name, attempt)
            self.broadcaster.stage_started(project_id, stage_name, attempt + 1)
            self.event_log.record(
                project_id, stage_name,
                f"Attempt {attempt + 1}: generating with the AI model...",
            )

            effective_context = (
                context if attempt == 0
                else self._build_retry_context(context, reviewer_feedback, attempt)
            )

            # ── Pre-flight context trim ───────────────────────────────
            # Guard against context-window overflow: if the assembled prompt
            # exceeds _MAX_CONTEXT_CHARS, trim it before hitting the LLM.
            # This is the last line of defence after the ContextBudget
            # enrichment limits have already been applied.
            effective_context = self._trim_context_for_model(effective_context)

            # ── Execute ──────────────────────────────────────────────
            try:
                exec_result = self.execution_manager.execute_stage(
                    project_id, stage_name, effective_context, attempt=attempt + 1,
                )
                artifact = exec_result.artifact
                # Capture the PREVIOUS attempt's summary before overwriting it.
                # previous_content is None on the first attempt (nothing to compare against)
                # and the prior artifact summary on retries — this avoids the first-attempt
                # false-positive where content == previous_content because both point at
                # the same freshly-generated artifact.
                prev_artifact_summary = last_artifact_summary if attempt > 0 else None
                last_artifact_summary = (artifact.content or "")[:300]
                arch_endpoints, arch_modules = self._load_architecture_context(project_id)
                review_result = self.reviewer.review(
                    artifact,
                    previous_content=prev_artifact_summary or None,
                    architecture_endpoints=arch_endpoints,
                    architecture_modules=arch_modules,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("stage attempt raised: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(
                    project_id, stage_name,
                    f"Attempt {attempt + 1} failed: {last_error}",
                    level="error",
                )
                self.broadcaster.stage_retry(project_id, stage_name, attempt + 2, last_error)
                failed_approaches.append(last_error)
                attempt += 1

                # Stop loop immediately on deterministic/unrecoverable errors
                # (missing agent, config, missing file) or after max 5 attempts.
                #
                # Context-overflow errors (HTTP 400 "input tokens exceed …") are
                # explicitly NOT deterministic — the pre-flight trim on the next
                # attempt will reduce the prompt size so the call can succeed.
                exc_type_name = type(exc).__name__
                exc_message = str(exc).lower()
                is_context_overflow = any(
                    marker in exc_message
                    for marker in _CONTEXT_OVERFLOW_MARKERS
                )
                is_deterministic = (
                    not is_context_overflow  # overflow is always recoverable
                    and (
                        isinstance(exc, (FileNotFoundError, ImportError, AttributeError))
                        or "DependencyException" in exc_type_name
                        or "ProviderValidationException" in exc_type_name
                        or "ConfigurationException" in exc_type_name
                    )
                )
                if attempt >= 5 or is_deterministic:
                    logger.error(
                        "stage %s failed after %d attempt(s) (deterministic/unrecoverable error): %s",
                        stage_name, attempt, exc,
                    )
                    break
                continue

            # ── Attempt hook (trajectory recording etc.) ─────────────
            if on_attempt is not None:
                try:
                    on_attempt(attempt, artifact, review_result)
                except Exception as _cb_exc:
                    logger.debug("on_attempt hook raised (non-fatal): %s", _cb_exc)

            # ── Approved ─────────────────────────────────────────────
            if review_result.approved:
                duration_sec = (datetime.now(timezone.utc) - stage_start).total_seconds()
                logger.info("stage approved: stage=%s attempt=%s", stage_name, attempt)
                self.event_log.record(
                    project_id, stage_name,
                    f"{stage_name} approved on attempt {attempt + 1}",
                )
                self.broadcaster.stage_complete(
                    project_id, stage_name, attempt + 1, duration_sec,
                )
                return StageRunResult(
                    success=True,
                    artifact=artifact,
                    message="approved",
                    attempt_count=attempt + 1,
                    failed_approaches=failed_approaches,
                    duration_sec=duration_sec,
                    review_result=review_result,
                )

            # ── Rejected ─────────────────────────────────────────────
            reviewer_feedback = self._detailed_feedback(review_result)
            logger.warning(
                "stage rejected: stage=%s attempt=%s feedback=%s",
                stage_name, attempt, reviewer_feedback,
            )
            self.event_log.record(
                project_id, stage_name,
                f"Attempt {attempt + 1} rejected: {review_result.overall_feedback}",
                level="warning",
            )
            failed_approaches.append(reviewer_feedback)

            if _engine_driven:
                # Engine is the primary gate: it decides whether to retry and
                # what instruction/config to use on the next attempt.
                retry_plan = self.retry_engine.plan(
                    attempt=attempt + 1,
                    review_result=review_result,
                    stage=stage_name,
                    project_id=project_id,
                )
                logger.debug(
                    "retry_engine decision: stage=%s attempt=%s strategy=%s "
                    "should_retry=%s rejection_type=%s config=%s",
                    stage_name, attempt, retry_plan.strategy,
                    retry_plan.should_retry, retry_plan.rejection_type,
                    retry_plan.modified_config or "{}",
                )
                if retry_plan.prompt_instruction:
                    reviewer_feedback = (
                        f"{reviewer_feedback}\n{retry_plan.prompt_instruction}"
                    )
                # Apply LLM config overrides for the *next* attempt only when
                # there will actually be a next attempt — avoids a spurious
                # set_stage_profile() call on the final stop decision.
                if retry_plan.should_retry and retry_plan.modified_config:
                    self._apply_retry_config(retry_plan.modified_config)
                self.broadcaster.stage_retry(
                    project_id, stage_name, attempt + 2, reviewer_feedback,
                )
                attempt += 1
                if retry_plan.should_stop:
                    break
            else:
                self.broadcaster.stage_retry(project_id, stage_name, attempt + 2, reviewer_feedback)
                attempt += 1

        # ── Retries exhausted ─────────────────────────────────────────
        logger.error("stage exhausted retries: stage=%s attempts=%s", stage_name, attempt)
        self.event_log.record(
            project_id, stage_name,
            f"{stage_name} failed after {attempt} attempt(s)",
            level="error",
        )
        self.broadcaster.stage_failed(
            project_id, stage_name, f"Exhausted retries ({attempt} attempts)",
        )

        if review_result is not None:
            message = review_result.overall_feedback
        elif last_error:
            message = f"{stage_name} could not run: {last_error}"
        else:
            message = "no execution attempted"

        return StageRunResult(
            success=False,
            artifact=None,
            message=message,
            attempt_count=attempt,
            failed_approaches=failed_approaches,
            review_result=review_result,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_retry_config(self, modified_config: dict) -> None:
        """Apply LLM config overrides from a RetryPlan to the next execute_stage call.

        Uses the same ``execution_manager.llm_manager.set_stage_profile()`` path
        that WorkflowEngine._apply_model_router_profile() uses.  The profile is
        consumed and cleared by LLMManager.generate_text() immediately after the
        next LLM call, so overrides are scoped to exactly one attempt.

        Non-fatal: any failure is logged and silently ignored so the retry loop
        continues regardless of whether the config could be applied.
        """
        if not modified_config:
            return
        llm = getattr(self.execution_manager, "llm_manager", None)
        if llm is None or not hasattr(llm, "set_stage_profile"):
            logger.debug(
                "_apply_retry_config: llm_manager not reachable via execution_manager; "
                "modified_config %s will not be applied",
                modified_config,
            )
            return
        try:
            from ..shared.dto.model_profile import ModelProfile
            profile = ModelProfile(
                provider="",   # empty → LLMManager keeps the configured provider
                model="",      # empty → LLMManager keeps the configured model
                max_tokens=modified_config.get("max_tokens"),
                temperature=modified_config.get("temperature"),
            )
            llm.set_stage_profile(profile)
            logger.debug(
                "_apply_retry_config: set_stage_profile applied: max_tokens=%s temperature=%s",
                profile.max_tokens, profile.temperature,
            )
        except Exception as exc:
            logger.debug("_apply_retry_config: non-fatal failure: %s", exc)

    @staticmethod
    def _build_retry_context(original: str, feedback: str, attempt: int) -> str:
        return (
            f"{original}\n\n"
            f"--- REVIEWER FEEDBACK (Attempt {attempt}) ---\n"
            f"Your previous output was rejected for the following reasons:\n"
            f"{feedback}\n"
            f"Please address all feedback points in your next response.\n"
            f"--- END FEEDBACK ---"
        )

    @staticmethod
    def _detailed_feedback(review_result: Any) -> str:
        if not review_result.findings:
            return review_result.overall_feedback
        lines = [review_result.overall_feedback]
        for finding in review_result.findings:
            line = f"- [{finding.tier.value}] {finding.description}"
            if finding.suggestion:
                line += f" -- Suggestion: {finding.suggestion}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _trim_context_for_model(
        context: str, limit: int = _MAX_CONTEXT_CHARS
    ) -> str:
        """Trim *context* so it fits within the model's context window.

        Strategy
        --------
        Keep the front 45 % (task description, requirements, architecture
        decisions) and the tail 35 % (most-recent sprint output, reviewer
        feedback) — 80 % total, leaving 20 % headroom beneath *limit*.
        The discarded middle contains older intermediate sprint deltas that
        are least relevant to the current attempt.

        A clearly labelled sentinel is injected where the content was removed
        so the model is aware that trimming occurred rather than encountering
        a silent mid-document truncation.

        Logs a WARNING when trimming occurs so ops can detect projects whose
        accumulated context systematically exceeds the safe cap.
        """
        if len(context) <= limit:
            return context

        front_chars = int(limit * 0.45)
        tail_chars = int(limit * 0.35)
        removed = len(context) - front_chars - tail_chars

        sentinel = (
            f"\n\n...[CONTEXT TRIMMED: {removed:,} characters of intermediate "
            f"sprint output removed to fit the model context window. "
            f"Focus on the task requirements above and the most-recent output below.]\n\n"
        )
        trimmed = context[:front_chars] + sentinel + context[-tail_chars:]
        logger.warning(
            "context trimmed for model: original_chars=%d trimmed_chars=%d limit=%d",
            len(context), len(trimmed), limit,
        )
        return trimmed

    def _load_architecture_context(
        self, project_id: str
    ) -> tuple[list[str] | None, list[dict] | None]:
        """Load Architecture artifact and extract endpoints + modules for cross-stage checks.

        Returns (endpoints, modules) where each is None when the artifact is
        unavailable (e.g., early Discovery stages before Architect has run).
        Both are used by Reviewer.review() to enable cross-stage consistency
        checks without requiring the reviewer to know how artifacts are stored.
        """
        if self.artifact_manager is None:
            return None, None
        try:
            from ..shared.enums.stage import Stage
            art = self.artifact_manager.get_artifact(project_id, Stage.Architect)
            if art is None or not art.structured_content:
                return None, None
            sc = art.structured_content
            # Endpoints: list of "METHOD /path" strings for Design cross-check
            raw_endpoints = sc.get("api_endpoints") or sc.get("api_design") or []
            endpoints: list[str] = []
            for ep in raw_endpoints:
                if isinstance(ep, dict):
                    method = ep.get("method", "")
                    path = ep.get("path", "")
                    if method and path:
                        endpoints.append(f"{method} {path}")
                elif isinstance(ep, str):
                    endpoints.append(ep)
            # Modules: list of dicts with "name" and optional "files"
            raw_modules = sc.get("modules") or []
            modules: list[dict] = []
            for mod in raw_modules:
                if isinstance(mod, dict):
                    modules.append(mod)
                elif hasattr(mod, "name"):
                    # Pydantic ModuleSpec object
                    modules.append({"name": mod.name, "files": list(getattr(mod, "files", []) or [])})
            return endpoints or None, modules or None
        except Exception as exc:
            logger.debug("stage_runner: could not load architecture context for %s: %s", project_id, exc)
            return None, None

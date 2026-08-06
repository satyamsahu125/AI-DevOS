from __future__ import annotations

import logging
import re
from enum import Enum

from pydantic import BaseModel, Field

from ..memory.learning_loop import LearningLoop, Trajectory
from ..shared.models.stage_artifact import StageArtifact

logger = logging.getLogger(__name__)

_ASK_HUMAN_MIN_CHARS = 10
_LOW_QUALITY_SHORT_CHARS = 30
_QUALITY_FLAG_THRESHOLD = 0.6
_HIGH_TOKEN_ESTIMATE_CHARS = 8000

_DESIGN_SCHEMA_NAME = "WriteDesign"
_DESIGN_MIN_USER_FLOWS = 3
_REQUIRED_DESIGN_SYSTEM_KEYS = ("colors", "fonts", "spacing", "breakpoints")

_CODE_SCHEMA_NAMES = ("WriteBackendFiles", "WriteFrontendFiles")
_CODE_COVERAGE_FLAG_THRESHOLD = 0.5

# Minimum word count for non-empty text-only stages (StrategicReview, Retro, Security)
_MIN_WORDS_TEXT_STAGE = 30

# Boilerplate phrases common in LLM hallucinated/degenerate responses
_BOILERPLATE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bsure[,!]?\s+(here|i\'ll|let me)\b", re.IGNORECASE),
    re.compile(r"\bhere is (your|the|a)\b", re.IGNORECASE),
    re.compile(r"\bcertainly[,!]?\s+here\b", re.IGNORECASE),
    re.compile(r"\bof course[,!]?\s+here\b", re.IGNORECASE),
    re.compile(r"\bi (am|will|would) (happy|glad) to\b", re.IGNORECASE),
    re.compile(r"\bas (an|a) (AI|language model|LLM)\b", re.IGNORECASE),
]

# Required top-level keys per schema — if any are empty/missing it indicates a truncated
# or stub output. Split into two tiers:
#   CRITICAL → empty required key blocks approval (ASK_HUMAN): these stages gate the whole pipeline.
#   NON_CRITICAL → empty required key is advisory only (FLAG): later/release stages.
_REQUIRED_STRUCTURED_KEYS: dict[str, list[str]] = {
    "WriteArchitecture":  ["modules", "api_endpoints", "data_models"],
    "WriteDesign":        ["user_flows", "components", "page_layouts"],
    "WriteRequirements":  ["requirements"],
    "WriteStrategicBrief": ["goals", "risks"],
    "WriteSecurityReport": ["threats", "recommendations"],
    "WriteQAReport":      ["test_cases"],
    "WriteDeployment":    ["infrastructure", "deployment_steps"],
    # FileStructurePlanner: empty files list means both dev stages will find nothing to write.
    # Must be critical so the retry loop in WriteFilePlanAction._parse_structured kicks in.
    "WriteFilePlan":      ["files"],
}

# Schemas whose empty required keys escalate to ASK_HUMAN (block approval).
# These stages directly gate every downstream stage — a stub output here means
# BackendDev / FrontendDev / QA will all receive unusable context.
_CRITICAL_SCHEMAS: frozenset[str] = frozenset({
    "WriteArchitecture",
    "WriteRequirements",
    "WriteDesign",
    "WriteBackendFiles",
    "WriteFrontendFiles",
    "WriteFilePlan",
})


class ReviewTier(str, Enum):
    """How urgently a ReviewFinding needs attention (inspired by gstack's /review Fix-First heuristic)."""

    AUTO_FIX = "auto_fix"
    ASK_HUMAN = "ask_human"
    FLAG = "flag"


class ReviewFinding(BaseModel):
    """One issue Reviewer noticed, tagged with how it should be handled."""

    tier: ReviewTier
    description: str
    file: str | None = None
    suggestion: str = ""


class ReviewResult(BaseModel):
    """The outcome of Reviewer.review(): approval plus every finding, grouped by tier."""

    approved: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    auto_fixes_applied: list[str] = Field(default_factory=list)
    human_questions: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    overall_feedback: str = ""
    quality_score: float = 0.0


class Reviewer:
    """Three-tier artifact reviewer (inspired by gstack's /review Fix-First heuristic).

    Every finding is tagged AUTO_FIX (mechanical, doesn't block), ASK_HUMAN
    (blocks approval -- something a reasonable engineer would want a human
    decision on), or FLAG (advisory, noted but never blocking) -- mirroring
    gstack's rule of thumb: "if the fix is mechanical, AUTO-FIX; if
    reasonable engineers could disagree, ASK."

    approved is True only when there are no ASK_HUMAN findings and the
    content itself is valid (non-empty). AUTO_FIX and FLAG findings never
    block approval on their own.
    """

    def __init__(self, learning_loop: LearningLoop | None = None) -> None:
        """Wire the LearningLoop findings are recorded to as failure trajectories."""
        self.learning_loop = learning_loop or LearningLoop()

    def review(
        self, artifact: StageArtifact, previous_content: str | None = None,
        architecture_endpoints: list[str] | None = None,
    ) -> ReviewResult:
        """Review artifact, optionally comparing against previous_content (the prior attempt's output).

        architecture_endpoints is only consulted for Designer-stage artifacts
        (schema_type == "WriteDesign"), to cross-check api_dependencies
        against the real ArchitectureArtifact endpoints; omit it to skip
        that specific cross-check.
        """
        content = (artifact.content or "").strip()
        content_valid = bool(content)

        findings: list[ReviewFinding] = []
        auto_fixes_applied: list[str] = []
        human_questions: list[str] = []
        flags: list[str] = []

        self._check_auto_fix(artifact, content_valid, findings, auto_fixes_applied)
        self._check_ask_human(artifact, content, content_valid, findings, human_questions)
        quality_score = self._compute_quality_score(artifact, content, content_valid)
        self._check_flag(artifact, content, quality_score, previous_content, findings, flags, human_questions)
        if artifact.schema_type == _DESIGN_SCHEMA_NAME and artifact.structured_content:
            self._check_design_stage(artifact, architecture_endpoints, findings, auto_fixes_applied, human_questions, flags)
        if artifact.schema_type in _CODE_SCHEMA_NAMES and artifact.structured_content:
            self._check_code_stage(artifact, findings, human_questions, flags)

        approved = content_valid and not human_questions
        overall_feedback = self._summarize(approved, findings)

        result = ReviewResult(
            approved=approved,
            findings=findings,
            auto_fixes_applied=auto_fixes_applied,
            human_questions=human_questions,
            flags=flags,
            overall_feedback=overall_feedback,
            quality_score=quality_score,
        )
        self._record_finding_patterns(artifact, result)
        return result

    def _check_auto_fix(
        self, artifact: StageArtifact, content_valid: bool,
        findings: list[ReviewFinding], auto_fixes_applied: list[str],
    ) -> None:
        """Detect AUTO_FIX patterns: empty content is the mechanical case -- nothing to salvage, just flag it."""
        if not content_valid:
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description="Artifact content is empty",
                suggestion="Regenerate the stage output",
            )
            findings.append(finding)
            auto_fixes_applied.append("flagged empty content for regeneration")
            logger.warning("auto-fix: %s", finding.description)

    def _check_ask_human(
        self, artifact: StageArtifact, content: str, content_valid: bool,
        findings: list[ReviewFinding], human_questions: list[str],
    ) -> None:
        """Detect ASK_HUMAN patterns: missing structured output where a schema was expected, or ambiguous output."""
        if artifact.schema_type and not artifact.structured_content:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description=f"Expected structured output for schema '{artifact.schema_type}' but none was produced",
                suggestion="Ask the agent to retry with stricter JSON-only instructions",
            )
            findings.append(finding)
            human_questions.append(finding.description)
            logger.info("ask-human: %s", finding.description)

        if content_valid and len(content) < _ASK_HUMAN_MIN_CHARS:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="Artifact content is too short to be a usable stage output",
                suggestion="Confirm this is intentional or ask the agent to elaborate",
            )
            findings.append(finding)
            human_questions.append(finding.description)
            logger.info("ask-human: %s", finding.description)

    def _check_flag(
        self, artifact: StageArtifact, content: str, quality_score: float, previous_content: str | None,
        findings: list[ReviewFinding], flags: list[str], human_questions: list[str] | None = None,
    ) -> None:
        """Detect FLAG/ASK_HUMAN patterns: low quality score, unusually long content, repeated content,
        boilerplate phrasing, and empty required structured fields (critical schemas → ASK_HUMAN)."""
        if human_questions is None:
            human_questions = []
        if quality_score < _QUALITY_FLAG_THRESHOLD:
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description=f"Quality score {quality_score:.2f} is below the {_QUALITY_FLAG_THRESHOLD:.2f} threshold",
                suggestion="Review manually before relying on this artifact",
            )
            findings.append(finding)
            flags.append(finding.description)

        if len(content) > _HIGH_TOKEN_ESTIMATE_CHARS:
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description="Artifact content is unusually long (possible runaway generation)",
                suggestion="Check for repetition or truncation",
            )
            findings.append(finding)
            flags.append(finding.description)

        if previous_content is not None and content and content == previous_content.strip():
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description="Artifact content is identical to the previous attempt",
                suggestion="The agent may be stuck repeating itself",
            )
            findings.append(finding)
            flags.append(finding.description)

        # Boilerplate detection: LLM assistant-voice phrases in structured output
        for pattern in _BOILERPLATE_PATTERNS:
            if pattern.search(content[:500]):
                finding = ReviewFinding(
                    tier=ReviewTier.FLAG,
                    description="Content begins with LLM boilerplate phrasing (assistant voice leaked into output)",
                    suggestion="Re-prompt with stricter 'output JSON only, no preamble' instruction",
                )
                findings.append(finding)
                flags.append(finding.description)
                break  # one flag per artifact is enough

        # Word count check for text-only (non-structured) stages
        if not artifact.schema_type and content:
            word_count = len(content.split())
            if word_count < _MIN_WORDS_TEXT_STAGE:
                finding = ReviewFinding(
                    tier=ReviewTier.FLAG,
                    description=f"Text-stage output is very short ({word_count} words, minimum {_MIN_WORDS_TEXT_STAGE})",
                    suggestion="The agent may have produced a stub response; check for completeness",
                )
                findings.append(finding)
                flags.append(finding.description)

        # Structured content required-key emptiness check.
        # Critical schemas (Architect, Requirements, Design, BackendDev, FrontendDev)
        # gate the entire downstream pipeline — empty required fields escalate to
        # ASK_HUMAN (blocks approval). Non-critical schemas get FLAG (advisory only).
        #
        # Special case for WriteArchitecture: api_endpoints and data_models can
        # legitimately be empty for static-frontend / simple projects. The
        # WriteArchitectureAction already guards the fully-empty case (no modules,
        # no endpoints, no models). Here we only raise ASK_HUMAN if *modules*
        # itself is empty — that is ALWAYS wrong. Empty api_endpoints/data_models
        # alone is demoted to FLAG so the pipeline can continue.
        required_keys = _REQUIRED_STRUCTURED_KEYS.get(artifact.schema_type or "", [])
        if required_keys and artifact.structured_content:
            empty_required = [
                k for k in required_keys
                if not artifact.structured_content.get(k)
            ]
            if empty_required:
                is_critical = (artifact.schema_type or "") in _CRITICAL_SCHEMAS

                # For WriteArchitecture, split into truly-blocking vs advisory empties.
                if is_critical and artifact.schema_type == "WriteArchitecture":
                    blocking = [k for k in empty_required if k == "modules"]
                    advisory = [k for k in empty_required if k != "modules"]
                    if advisory:
                        finding = ReviewFinding(
                            tier=ReviewTier.FLAG,
                            description=(
                                f"Architecture fields are empty: {', '.join(advisory)}. "
                                "This may be intentional for simple / static-frontend projects."
                            ),
                            suggestion=(
                                "If this is a full-stack project, retry with higher max_tokens "
                                "or switch to Claude/Gemini. If frontend-only, this is expected."
                            ),
                        )
                        findings.append(finding)
                        flags.append(finding.description)
                        logger.warning(
                            "reviewer: advisory empty fields stage=%s empty=%s",
                            artifact.schema_type, advisory,
                        )
                    empty_required = blocking  # only block on missing modules

                if empty_required:
                    if is_critical:
                        finding = ReviewFinding(
                            tier=ReviewTier.ASK_HUMAN,
                            description=(
                                f"Critical stage '{artifact.schema_type}' produced empty required fields: "
                                f"{', '.join(empty_required)}. Downstream stages cannot proceed."
                            ),
                            suggestion="Retry with higher max_tokens, switch to Claude/Gemini provider, or reduce prompt context",
                        )
                        findings.append(finding)
                        human_questions.append(finding.description)
                        logger.warning(
                            "reviewer: critical schema empty fields stage=%s empty=%s",
                            artifact.schema_type, empty_required,
                        )
                    else:
                        finding = ReviewFinding(
                            tier=ReviewTier.FLAG,
                            description=f"Required structured fields are empty: {', '.join(empty_required)}",
                            suggestion="Agent likely produced a stub output — retry with higher max_tokens or slim context",
                        )
                        findings.append(finding)
                        flags.append(finding.description)

    def _check_design_stage(
        self, artifact: StageArtifact, architecture_endpoints: list[str] | None,
        findings: list[ReviewFinding], auto_fixes_applied: list[str],
        human_questions: list[str], flags: list[str],
    ) -> None:
        """Designer-stage-specific checks layered on top of the generic three-tier review."""
        structured = artifact.structured_content
        design_system = structured.get("design_system") or {}
        user_flows = structured.get("user_flows") or []
        components = structured.get("components") or []
        page_layouts = structured.get("page_layouts") or []
        api_dependencies = structured.get("api_dependencies") or []
        accessibility_notes = structured.get("accessibility_notes") or []

        # AUTO_FIX: missing design_system fields -> fill with defaults.
        missing_keys = [key for key in _REQUIRED_DESIGN_SYSTEM_KEYS if key not in design_system]
        if missing_keys:
            for key in missing_keys:
                design_system[key] = {}
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description=f"design_system was missing {', '.join(missing_keys)} -- filled with empty defaults",
                suggestion="Confirm the defaults are acceptable or fill them in explicitly",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)

        # AUTO_FIX: components with no states -> add loading/error/empty/populated.
        for component in components:
            if not component.get("states"):
                component["states"] = ["loading", "error", "empty", "populated"]
                finding = ReviewFinding(
                    tier=ReviewTier.AUTO_FIX,
                    description=f"component '{component.get('name', '?')}' had no states defined -- added defaults",
                    suggestion="Confirm the default states are correct for this component",
                )
                findings.append(finding)
                auto_fixes_applied.append(finding.description)

        # ASK_HUMAN: user flows that don't connect (missing entry or both exits).
        for flow in user_flows:
            if not flow.get("entry_point") or not (flow.get("success_end") or flow.get("error_end")):
                finding = ReviewFinding(
                    tier=ReviewTier.ASK_HUMAN,
                    description=f"user flow '{flow.get('name', '?')}' is a dead end (missing entry point or exit point)",
                    suggestion="Define both an entry_point and at least one of success_end/error_end",
                )
                findings.append(finding)
                human_questions.append(finding.description)

        # ASK_HUMAN: components referencing API endpoints not in the architecture.
        if architecture_endpoints is not None:
            known_endpoints = set(architecture_endpoints)
            unknown = [dep for dep in api_dependencies if dep not in known_endpoints]
            if unknown:
                finding = ReviewFinding(
                    tier=ReviewTier.ASK_HUMAN,
                    description=f"api_dependencies reference endpoints not in the architecture: {', '.join(unknown)}",
                    suggestion="Confirm these endpoints exist, or update the architecture to include them",
                )
                findings.append(finding)
                human_questions.append(finding.description)

        # ASK_HUMAN: no accessibility notes at all.
        if not accessibility_notes:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="No accessibility notes were provided",
                suggestion="Document at least one accessibility consideration or assumption",
            )
            findings.append(finding)
            human_questions.append(finding.description)

        # ASK_HUMAN (approval gate): every page must have at least one component.
        if not page_layouts:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="No page layouts were defined",
                suggestion="Define at least one page layout with its component arrangement",
            )
            findings.append(finding)
            human_questions.append(finding.description)
        else:
            for layout in page_layouts:
                if not any(value for value in layout.values()):
                    finding = ReviewFinding(
                        tier=ReviewTier.ASK_HUMAN,
                        description=f"page layout {layout} has no components arranged",
                        suggestion="Every page must resolve to at least one component",
                    )
                    findings.append(finding)
                    human_questions.append(finding.description)

        # ASK_HUMAN: no user flows at all (a design spec with zero flows isn't usable).
        # FLAG: at least one flow exists but fewer than 3 (likely incomplete).
        if not user_flows:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="No user flows were defined at all",
                suggestion="Define at least one user flow with a clear entry point and exit point",
            )
            findings.append(finding)
            human_questions.append(finding.description)
        elif len(user_flows) < _DESIGN_MIN_USER_FLOWS:
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description=f"Only {len(user_flows)} user flow(s) defined (expected at least {_DESIGN_MIN_USER_FLOWS})",
                suggestion="Consider whether other user flows are missing",
            )
            findings.append(finding)
            flags.append(finding.description)

        # FLAG: no error states on any form component.
        form_components = [c for c in components if str(c.get("type", "")).lower() == "form"]
        if form_components and not any("error" in (c.get("states") or []) for c in form_components):
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description="No form component defines an error state",
                suggestion="Add an error state to at least one form component",
            )
            findings.append(finding)
            flags.append(finding.description)

        # FLAG: design system missing breakpoints (not responsive).
        if not design_system.get("breakpoints"):
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description="design_system has no breakpoints defined (not responsive)",
                suggestion="Define at least mobile/tablet/desktop breakpoints",
            )
            findings.append(finding)
            flags.append(finding.description)

    def _check_code_stage(
        self, artifact: StageArtifact, findings: list[ReviewFinding], human_questions: list[str], flags: list[str],
    ) -> None:
        """BackendDeveloper/FrontendDeveloper-specific holistic check: does the written file set
        match what the File Plan called for. Per-file plausibility is already enforced as each
        file is written (see WriteProjectFilesAction._is_plausible); this only asks whether the
        planned set was actually covered end to end."""
        structured = artifact.structured_content
        planned = structured.get("planned_paths") or []
        written = structured.get("written_paths") or []
        skipped = structured.get("skipped_paths") or []

        if not planned:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="No files were planned for this stage's area -- the File Plan may be missing or empty",
                suggestion="Confirm FileStructurePlanner assigned files to this stage before retrying",
            )
            findings.append(finding)
            human_questions.append(finding.description)
            return

        if skipped:
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description=f"{len(skipped)} planned file(s) were not written: {', '.join(skipped)}",
                suggestion="Retry generation for the skipped files",
            )
            findings.append(finding)
            human_questions.append(finding.description)

        coverage = len(written) / len(planned)
        if coverage < _CODE_COVERAGE_FLAG_THRESHOLD:
            finding = ReviewFinding(
                tier=ReviewTier.FLAG,
                description=f"Only {coverage:.0%} of planned files were written",
                suggestion="Review whether the remaining files are actually needed",
            )
            findings.append(finding)
            flags.append(finding.description)

    def _compute_quality_score(self, artifact: StageArtifact, content: str, content_valid: bool) -> float:
        """Heuristic 0.0-1.0 quality score used by the FLAG check."""
        if not content_valid:
            return 0.0
        score = 1.0
        if len(content) < _LOW_QUALITY_SHORT_CHARS:
            score -= 0.5
        if artifact.schema_type and not artifact.structured_content:
            score -= 0.3
        if artifact.safety_flags:
            score -= 0.1
        # Penalise empty required structured fields (stub/truncated output)
        required_keys = _REQUIRED_STRUCTURED_KEYS.get(artifact.schema_type or "", [])
        if required_keys and artifact.structured_content:
            empty_ratio = sum(
                1 for k in required_keys if not artifact.structured_content.get(k)
            ) / len(required_keys)
            score -= 0.4 * empty_ratio
        # Penalise boilerplate phrasing
        for pattern in _BOILERPLATE_PATTERNS:
            if pattern.search(content[:500]):
                score -= 0.2
                break
        return max(0.0, min(1.0, score))

    def _summarize(self, approved: bool, findings: list[ReviewFinding]) -> str:
        """Build a one-line overall feedback summary from approval status and finding counts."""
        if not findings:
            return "Approved: no issues found." if approved else "Rejected: content is invalid."
        by_tier: dict[ReviewTier, int] = {}
        for finding in findings:
            by_tier[finding.tier] = by_tier.get(finding.tier, 0) + 1
        tier_summary = ", ".join(f"{count} {tier.value}" for tier, count in by_tier.items())
        verdict = "Approved" if approved else "Rejected"
        return f"{verdict}: {tier_summary}."

    def _record_finding_patterns(self, artifact: StageArtifact, result: ReviewResult) -> None:
        """Record a rejected/flagged review as a failure trajectory, so future reviews can learn from it."""
        if result.approved and not result.findings:
            return
        trajectory = Trajectory(
            stage=artifact.schema_type or artifact.name,
            task_description=artifact.name,
            artifact_summary=(artifact.content or "")[:300],
            retry_count=0,
            approved=result.approved,
            reviewer_feedback=result.overall_feedback,
            agent_model="",
            tokens_used=0,
            latency_ms=0.0,
        )
        self.learning_loop.record_trajectory(trajectory)

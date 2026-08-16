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
# If stub_paths / written_paths ratio exceeds this, escalate to ASK_HUMAN.
_STUB_RATIO_ASK_HUMAN = 0.4

# Common module-name suffixes that are not meaningful for file-path matching.
# "AuthModule" → "auth", "UserService" → "user", etc.
_MODULE_NAME_STRIP_SUFFIXES = re.compile(
    r"(?:module|service|manager|controller|handler|repository|store|agent|layer|component)s?$",
    re.IGNORECASE,
)
# Splits CamelCase or snake_case into words for normalisation.
_CAMEL_SPLIT_RE = re.compile(r"[_\-\s]+|(?<=[a-z])(?=[A-Z])")

# Minimum word count for non-empty text-only stages (StrategicReview, Retro, Security)
_MIN_WORDS_TEXT_STAGE = 30

# Depth thresholds for specific structured stages
_MIN_SECURITY_THREATS = 2    # fewer → FLAG (shallow security analysis)
_MIN_ARCHITECTURE_MODULES = 2  # fewer → FLAG (may be a stub architecture)

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
        architecture_modules: list[dict] | None = None,
    ) -> ReviewResult:
        """Review artifact, optionally comparing against previous_content (the prior attempt's output).

        architecture_endpoints is consulted for Designer-stage artifacts to cross-check
        api_dependencies against the real ArchitectureArtifact endpoints.

        architecture_modules is consulted for BackendDeveloper/FrontendDeveloper artifacts
        to verify that every Architecture module has at least one written file — a
        cross-stage consistency check that catches the case where the LLM skipped an
        entire module without it appearing in skipped_paths.

        Omit either argument to skip that specific cross-check.
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
            self._check_code_stage(artifact, architecture_modules, findings, human_questions, flags)

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

        # Depth heuristics: catch shallow-but-not-empty structured outputs.
        # These are always FLAG (advisory) — they signal the AI produced a minimal
        # response without failing the schema check, not a hard pipeline blocker.
        schema = artifact.schema_type or ""
        structured = artifact.structured_content or {}

        if schema == "WriteSecurityReport":
            threats = structured.get("threats") or []
            if threats and len(threats) < _MIN_SECURITY_THREATS:
                finding = ReviewFinding(
                    tier=ReviewTier.FLAG,
                    description=(
                        f"Security report lists only {len(threats)} threat(s) "
                        f"(minimum {_MIN_SECURITY_THREATS} expected for a meaningful report)"
                    ),
                    suggestion="Re-run Security stage or manually add more threats before proceeding",
                )
                findings.append(finding)
                flags.append(finding.description)

        if schema == "WriteArchitecture":
            modules = structured.get("modules") or []
            if modules and len(modules) < _MIN_ARCHITECTURE_MODULES:
                finding = ReviewFinding(
                    tier=ReviewTier.FLAG,
                    description=(
                        f"Architecture defines only {len(modules)} module(s). "
                        "This may be intentional for a simple project, but likely indicates a stub response."
                    ),
                    suggestion="Confirm the project is genuinely single-module, or retry for fuller coverage",
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

        # AUTO_FIX: user flows that don't connect (missing entry or exits) -> add defaults
        for flow in user_flows:
            if not flow.get("entry_point"):
                flow["entry_point"] = "Main Screen"
            if not (flow.get("success_end") or flow.get("error_end")):
                flow["success_end"] = "Action Confirmed"
                flow["error_end"] = "Error Alert"
                finding = ReviewFinding(
                    tier=ReviewTier.AUTO_FIX,
                    description=f"user flow '{flow.get('name', '?')}' was missing exit points -- added defaults",
                    suggestion="Review flow endpoints",
                )
                findings.append(finding)
                auto_fixes_applied.append(finding.description)

        # AUTO_FIX: components referencing new API endpoints -> note for backend
        if architecture_endpoints is not None:
            known_endpoints = set(architecture_endpoints)
            unknown = [dep for dep in api_dependencies if dep not in known_endpoints]
            if unknown:
                finding = ReviewFinding(
                    tier=ReviewTier.AUTO_FIX,
                    description=f"api_dependencies reference {len(unknown)} new endpoint(s): {', '.join(unknown[:3])}",
                    suggestion="Backend Developer will implement these endpoints",
                )
                findings.append(finding)
                auto_fixes_applied.append(finding.description)

        # AUTO_FIX: accessibility notes
        if not accessibility_notes:
            accessibility_notes.extend([
                "WCAG 2.1 AA compliant color contrast ratios.",
                "Accessible keyboard navigation and visible focus rings.",
            ])
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description="No accessibility notes were provided -- added standard WCAG 2.1 AA guidelines",
                suggestion="Confirm accessibility guidelines",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)

        # AUTO_FIX: every page must have at least one component.
        if not page_layouts:
            comp_names = [c.get("name", "MainContent") for c in components] or ["MainContainer"]
            page_layouts.append({"main_page": comp_names})
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description="No page layouts were defined -- mapped components to main_page",
                suggestion="Review page layout mappings",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)
        else:
            for layout in page_layouts:
                if not any(value for value in layout.values()):
                    layout["main_page"] = [c.get("name", "Component") for c in components] or ["MainContainer"]
                    finding = ReviewFinding(
                        tier=ReviewTier.AUTO_FIX,
                        description=f"page layout was empty -- populated with available components",
                        suggestion="Confirm component arrangement",
                    )
                    findings.append(finding)
                    auto_fixes_applied.append(finding.description)

        # AUTO_FIX: ensure at least 3 user flows
        if not user_flows:
            user_flows.append({
                "name": "Main User Flow",
                "steps": ["Open App", "Interact with Features", "Complete Action"],
                "entry_point": "Dashboard",
                "success_end": "Action Confirmed",
                "error_end": "Error Toast",
            })
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description="No user flows were defined -- added default user flow",
                suggestion="Review user flow steps",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)
        elif len(user_flows) < _DESIGN_MIN_USER_FLOWS:
            # AUTO_FIX: Auto-expand user flows to meet the minimum required count
            for idx in range(len(user_flows) + 1, _DESIGN_MIN_USER_FLOWS + 1):
                user_flows.append({
                    "name": f"Secondary User Flow {idx}",
                    "steps": ["Navigate to section", "Perform interaction", "View result"],
                    "entry_point": "Main View",
                    "success_end": "Action Completed",
                    "error_end": "Notification Shown",
                })
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description=f"Only {len(user_flows) - (_DESIGN_MIN_USER_FLOWS - len(user_flows))} user flow(s) defined -- added fallback flows to reach {_DESIGN_MIN_USER_FLOWS}",
                suggestion="Confirm the auto-generated secondary user flows match requirements",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)

        # AUTO_FIX: ensure form components define error state
        form_components = [c for c in components if str(c.get("type", "")).lower() == "form"]
        for c in form_components:
            states = c.setdefault("states", [])
            if "error" not in states:
                states.append("error")
                finding = ReviewFinding(
                    tier=ReviewTier.AUTO_FIX,
                    description=f"Form component '{c.get('name', '?')}' had no error state -- added 'error'",
                    suggestion="Ensure form error state is rendered in UI",
                )
                findings.append(finding)
                auto_fixes_applied.append(finding.description)

        # AUTO_FIX: design system missing breakpoints (add standard responsive breakpoints)
        if not design_system.get("breakpoints"):
            design_system["breakpoints"] = {"mobile": "640px", "tablet": "768px", "desktop": "1024px"}
            finding = ReviewFinding(
                tier=ReviewTier.AUTO_FIX,
                description="design_system had no breakpoints defined -- added responsive defaults",
                suggestion="Define custom mobile/tablet/desktop breakpoints if needed",
            )
            findings.append(finding)
            auto_fixes_applied.append(finding.description)

    @staticmethod
    def _normalise_module_name(name: str) -> str:
        """Reduce a module name to its meaningful root token for file-path matching.

        "AuthenticationModule" → "authentication"
        "UserService"          → "user"
        "payment_processor"    → "payment"
        """
        # Strip common suffix words first, then split on camel/snake boundary
        stripped = _MODULE_NAME_STRIP_SUFFIXES.sub("", name).strip()
        tokens = [t.lower() for t in _CAMEL_SPLIT_RE.split(stripped) if t]
        # Return the first meaningful token (usually the domain noun)
        return tokens[0] if tokens else name.lower()

    def _check_code_stage(
        self,
        artifact: StageArtifact,
        architecture_modules: list[dict] | None,
        findings: list[ReviewFinding],
        human_questions: list[str],
        flags: list[str],
    ) -> None:
        """BackendDeveloper/FrontendDeveloper-specific holistic checks.

        Three concerns:
        1. Coverage — were all planned files written?
        2. Stubs — did the LLM scaffold files without implementing them?
        3. Cross-stage consistency — does every Architecture module have ≥1 written file?
           (architecture_modules must be supplied by the caller; omit to skip this check.)
        """
        structured = artifact.structured_content
        planned = structured.get("planned_paths") or []
        written = structured.get("written_paths") or []
        skipped = structured.get("skipped_paths") or []
        stub_paths = structured.get("stub_paths") or []

        if not planned:
            # Distinguish two cases:
            #   (a) valid no-op: file plan has files but none for this stage
            #       (e.g. a mobile-only project has no backend files → BackendDeveloper
            #       should pass silently without blocking the pipeline).
            #   (b) real problem: file plan was empty / not loaded at all.
            # WriteProjectFilesAction writes "total_planned_in_file_plan" (total across
            # all stages) into structured so we can tell the two apart here.
            total_in_plan = structured.get("total_planned_in_file_plan", 0)
            if total_in_plan > 0:
                # File plan has files for OTHER stages; this stage just has nothing to do.
                # Log and return without adding any finding — the stage is implicitly approved.
                logger.info(
                    "reviewer: code stage %s is a valid no-op "
                    "(%d file(s) in plan, 0 assigned to this stage) — no finding",
                    artifact.schema_type, total_in_plan,
                )
                return
            # File plan was empty or not loaded — real problem; block with ASK_HUMAN.
            finding = ReviewFinding(
                tier=ReviewTier.ASK_HUMAN,
                description="No files were planned for this stage's area -- the File Plan may be missing or empty",
                suggestion="Confirm FileStructurePlanner assigned files to this stage before retrying",
            )
            findings.append(finding)
            human_questions.append(finding.description)
            return

        # ── Coverage checks ──────────────────────────────────────────────────
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

        # ── Stub-body detection ──────────────────────────────────────────────
        # stub_paths are files where WriteProjectFilesAction detected ≥2
        # function definitions whose body is only "pass". This means the LLM
        # scaffolded the file but did not implement it.
        if stub_paths:
            written_count = len(written) or 1
            stub_ratio = len(stub_paths) / written_count
            tier = ReviewTier.ASK_HUMAN if stub_ratio >= _STUB_RATIO_ASK_HUMAN else ReviewTier.FLAG
            description = (
                f"{len(stub_paths)} file(s) contain unimplemented stub bodies "
                f"(pass-only functions): {', '.join(stub_paths)}"
            )
            suggestion = (
                "These files were scaffolded but not implemented. "
                "Retry the stage with a stricter system prompt enforcing real logic."
                if tier == ReviewTier.ASK_HUMAN
                else "Review these files and confirm the stub bodies are intentional (e.g., abstract base classes)."
            )
            finding = ReviewFinding(tier=tier, description=description, suggestion=suggestion)
            findings.append(finding)
            if tier == ReviewTier.ASK_HUMAN:
                human_questions.append(description)
            else:
                flags.append(description)
            logger.info("reviewer: stub detection %s for stage=%s stubs=%s", tier.value, artifact.schema_type, stub_paths)

        # ── Cross-stage consistency: Architecture modules → written files ─────
        # For each module the Architect defined, check that at least one written
        # file path contains the module's normalised name.  A module with zero
        # coverage means the LLM silently omitted an entire domain area without
        # it showing up in skipped_paths.
        #
        # This is always FLAG (never ASK_HUMAN) because:
        #   • Multi-sprint projects legitimately write some modules later.
        #   • Module-name ↔ file-path matching is heuristic and can miss aliases.
        if architecture_modules and written:
            written_lower = " ".join(written).lower()
            uncovered: list[str] = []
            for mod in architecture_modules:
                mod_name = mod.get("name") or ""
                if not mod_name:
                    continue
                # Also check explicit file paths the Architect declared for this module
                declared_files: list[str] = mod.get("files") or []
                if any(f.lower() in written_lower for f in declared_files if f):
                    continue  # at least one declared file was written
                token = self._normalise_module_name(mod_name)
                if token and token not in written_lower:
                    uncovered.append(mod_name)
            if uncovered:
                finding = ReviewFinding(
                    tier=ReviewTier.FLAG,
                    description=(
                        f"{len(uncovered)} Architecture module(s) have no matching written file: "
                        f"{', '.join(uncovered)}"
                    ),
                    suggestion=(
                        "These modules may be planned for a later sprint, or the LLM silently "
                        "omitted them. Verify coverage before the release phase."
                    ),
                )
                findings.append(finding)
                flags.append(finding.description)
                logger.info(
                    "reviewer: cross-stage gap stage=%s uncovered_modules=%s",
                    artifact.schema_type, uncovered,
                )

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

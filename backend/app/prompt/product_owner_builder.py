from __future__ import annotations

from .builder import PromptBuilder

SYSTEM_PROMPT = """
You are a Senior Product Manager with 15 years experience.
You have shipped products used by millions of people.

YOUR BIGGEST RULE — NEVER WRITE GENERIC PLACEHOLDERS:
  BAD: "Goals: Implement requested product features"
  BAD: "As a user I want full functionality"
  GOOD: "REQ-001: User can perform addition of two numbers
         by clicking the + button. Result displays immediately."
  GOOD: "As Sarah (casual user), I want to divide 1500 by 12
         so I can calculate my monthly budget in seconds."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU RECEIVE (in the context JSON below)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  The context is a JSON object with these keys:
    original_request   — the user's verbatim project request
    clarification      — ClarificationArtifact from Q&A (your PRIMARY input)
    strategic_brief    — StrategicBrief produced by StrategicReview
    domain_research    — DomainBrief (optional; may be empty)

  If any key is absent or empty, use whatever is available.
  Never output {"error": "Missing..."} — always produce a best-effort PRD.

CRITICAL: Read explicit_non_requirements from clarification.
These become your OUT OF SCOPE list.
If Q&A says "NO authentication required", your PRD must say
exactly that — and the Architect must never add auth modules.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE OF YOUR OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PROJECT SUMMARY
   project_name: (specific name, not "Software Application")
   tagline: (one sentence describing the product)
   problem_statement: (specific problem being solved)
   target_users: (from Q&A — specific people, not archetypes)
   scale_profile: (from Q&A — how many users, what infrastructure)

2. PERSONAS (2-3 specific people)
   Name, age, role, device they use, their specific goal,
   their specific pain point that this app solves.

   EXAMPLE (not generic):
   Sarah, 28, works in sales, uses iPhone and Chrome.
   She calculates commissions daily and currently reaches
   for Windows Calculator but finds it slow to open.
   She needs fast arithmetic in the browser, nothing more.

3. FUNCTIONAL REQUIREMENTS (with REQ-IDs)
   Priority MUST: core functionality without which app is useless
   Priority SHOULD: important but not launch-blocking
   Priority COULD: nice to have in future
   Priority WONT: explicitly out of scope

   Each requirement has:
     req_id: "REQ-001"
     priority: "MUST"
     category: "Core Calculation"
     description: (specific to THIS app)
     given: (setup state)
     when: (user action)
     then: (expected result)
     edge_cases: (what happens in error states)

   CALCULATOR EXAMPLE:
     REQ-001 | MUST | Core Calculation
     Description: User can perform addition of two numbers
     Given: User has opened the calculator
     When: User enters 5, clicks +, enters 3, clicks =
     Then: Display shows 8 immediately
     Edge case: If = clicked with no second number,
                show first number unchanged

4. NON-FUNCTIONAL REQUIREMENTS
   From scale_profile:
     If database_needed=false: "No database required"
     If database_needed=true:  "Database required (see scale_profile)"
     If auth_needed=false: "No authentication required"
     If auth_needed=true:  "Authentication required (see scale_profile)"
   Performance: (specific numbers from scale profile)
   Platform: (from Q&A — web/mobile/ML/CLI/etc.)
   Browser support: (from Q&A — N/A for mobile, ML, CLI projects)

   CRITICAL: Copy project_type verbatim from clarification into
   non_functional_requirements.project_type. This is read by the Architect
   and every downstream stage. Never omit or rename it.

   Also copy tech_preferences from clarification into
   non_functional_requirements.tech_preferences if present.

5. USER STORIES (INVEST format)
   Each story must:
     - Reference a specific persona by name
     - Have a specific measurable benefit
     - Have testable acceptance criteria

6. OUT OF SCOPE (from explicit_non_requirements in Q&A)
   Copy the explicit_non_requirements list directly here.
   These become hard constraints for the Architect.

   CRITICAL CONSISTENCY CHECK — before writing out_of_scope:
     If scale_profile.auth_needed=true, you MUST NOT include
     any "No authentication" item in out_of_scope or constraints.
     Doing so creates a contradiction the Architect cannot resolve.

     If scale_profile.database_needed=true, you MUST NOT include
     any "No database" item in out_of_scope or constraints.

   The scale_profile flags are ground truth. If explicit_non_requirements
   from Q&A conflicts with a TRUE flag, the flag wins — do not copy
   the conflicting item into out_of_scope.

   Example for calculator (auth_needed=false, database_needed=false):
     - No user authentication or accounts
     - No database or server-side storage
     - No financial calculations
     - No user history

   Example for SaaS app (auth_needed=true, database_needed=true):
     - No payment processing (if not requested)
     - No mobile app (web only)
     — Authentication and database are IN SCOPE, do not list them here

7. OPEN QUESTIONS
   Only list questions that BLOCK development.
   Not preferences — actual blockers.

8. SUCCESS METRICS
   Measurable. Not "users like it."
   Example: "Calculator loads in < 1 second on 3G connection"
"""


class ProductOwnerPromptBuilder(PromptBuilder):
    """Advanced prompt builder for Product Owner stage."""

    def __init__(self) -> None:
        super().__init__(role="Product Owner")

    def build(self, context: object | None = None) -> str:
        import json as _json
        import re as _re

        raw = ""
        if context is not None:
            raw = context if isinstance(context, str) else _json.dumps(context, indent=2)

        # ── Path A: JSON block from _handle_qa_flow ──────────────────────────
        # Format: {"original_request":…, "clarification":…, "domain_research":…}
        if raw.strip().startswith("{"):
            try:
                ctx = _json.loads(raw)
                # Detect if the JSON IS a StrategicBrief (has "vision" key) vs
                # our wrapper dict (has "original_request" key).
                if "original_request" in ctx:
                    strategic = ctx.get("strategic_brief") or {}
                    agent_context: dict = {
                        "original_request": ctx.get("original_request", ""),
                        "clarification":    ctx.get("clarification", {}),
                        "strategic_brief":  strategic,
                        "domain_research":  ctx.get("domain_research", {}),
                    }
                else:
                    # The JSON itself is the StrategicBrief (vision/scope etc.)
                    agent_context = {
                        "original_request": "",
                        "clarification":    {},
                        "strategic_brief":  ctx,
                        "domain_research":  {},
                    }
            except (ValueError, TypeError):
                agent_context = {"original_request": raw, "clarification": {},
                                 "strategic_brief": {}, "domain_research": {}}

        # ── Path B: Predecessor-enriched string from WorkflowEngine ──────────
        # Format: "{request}\n\n### Previous Stage Output (StrategicReview)\n{json}"
        elif "### Previous Stage Output" in raw:
            split_pat = _re.compile(r"### Previous Stage Output[^\n]*\n", _re.IGNORECASE)
            parts = split_pat.split(raw, maxsplit=1)
            original_req = parts[0].strip() if parts else raw
            predecessor_raw = parts[1].strip() if len(parts) > 1 else ""
            strategic: dict = {}
            try:
                if predecessor_raw.strip().startswith("{"):
                    strategic = _json.loads(predecessor_raw)
            except (ValueError, TypeError):
                strategic = {}
            agent_context = {
                "original_request": original_req,
                "clarification":    {},   # not in predecessor chain at this point
                "strategic_brief":  strategic,
                "domain_research":  {},
            }

        # ── Path C: Plain string (skip_qa / legacy) ───────────────────────────
        else:
            agent_context = {
                "original_request": raw,
                "clarification":    {},
                "strategic_brief":  {},
                "domain_research":  {},
            }

        context_block = (
            "CONTEXT (agent-readable JSON — read every field before writing):\n"
            + _json.dumps(agent_context, indent=2)
        )

        return f"{SYSTEM_PROMPT}\n\n{context_block}\n\nProduce the full PRD as a single JSON object."

from __future__ import annotations

from .builder import PromptBuilder
from .context_extractor import SlimContextExtractor

_ROLE_BRIEFING = """You are updating documentation to match what was just shipped.
(Inspired by gstack's /document-release persona: every doc accurate and up to date,
written in a friendly, user-forward voice.)

Core responsibilities:
- Classify what changed: new features, changed behavior, removed functionality.
- Check documentation coverage (reference, how-to, tutorial, explanation) for what changed.
- Flag critical gaps (zero coverage) versus common gaps (partial coverage).

Quality criteria:
- Every doc edit has a one-line "what specifically changed" summary, not "updated docs."
- Every documented feature is discoverable from the project's main entry-point docs.

Common mistakes to avoid:
- Vague changelog entries that don't say what changed or why it matters.
- Auto-generating narrative/subjective documentation instead of flagging it for review."""

# Fields Document stage needs — just enough to know what was built.
# Full pipeline context can exceed 30K tokens; docs only needs the project name,
# tech stack, API surface, and list of generated files.
_DOC_KEYS = frozenset({
    "project_name",
    "tech_stack",
    "api_endpoints",     # what endpoints exist (names + methods)
    "modules",           # what backend modules were built
    "components",        # what frontend components were built
    "written_paths",     # from code stage: files actually produced
    "deployment_steps",  # from DevOps: how to run/deploy
})

class DocumentPromptBuilder(PromptBuilder, SlimContextExtractor):
    """Prompt builder for the Document stage.

    Uses SlimContextExtractor to pull only documentation-relevant fields, saving
    ~85% of context tokens vs passing the full 20-30 KB accumulated artifact chain.
    """

    def build(self, context: object | None = None) -> str:
        raw_content = self.get_raw_content(context)
        slim = self.extract(raw_content, _DOC_KEYS)
        if slim:
            body = f"Document Prompt:\nProject context (documentation-relevant fields):\n{slim}"
        else:
            body = f"Document Prompt:\nContext: {raw_content[:3000]}" if raw_content else "Document Prompt"
        return f"{_ROLE_BRIEFING}\n\n{body}"

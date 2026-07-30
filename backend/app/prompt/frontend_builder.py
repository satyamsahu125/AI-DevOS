from __future__ import annotations

from .builder import PromptBuilder
from .context_extractor import SlimContextExtractor

_ROLE_BRIEFING = """You are a Staff Frontend Engineer implementing sleek, production-ready React applications using modern 2026 UI ecosystem standards.

KNOWN IMPORT PATTERNS:
  shadcn: from "@/components/ui/button" import { Button }
  Magic UI: from "@/components/magicui/animated-beam" import { AnimatedBeam }
  Aceternity: from "@/components/ui/3d-card" import { CardContainer }
  Tremor: from "@tremor/react" import { AreaChart, MetricCard }
  Lucide: from "lucide-react" import { Home, Settings, User }
  Motion: from "framer-motion" import { motion, AnimatePresence }

INSTALL COMMANDS (add to generated package.json):
  npm install @tremor/react
  npm install framer-motion
  npm install sonner
  npx shadcn add [component-name]

When generating frontend files:
  1. Read design spec for this component
  2. Use EXACT shadcn_component from spec
  3. Use EXACT tailwind_classes from spec
  4. Add animation_component if specified
  5. Include all 5 states (default, hover, active, disabled, loading)
  6. Include dark mode variant (dark: classes)
  7. Include responsive breakpoints (sm: md: lg: xl: 2xl:)
  8. Clean Import Paths & Relative Dependencies: Use standard relative import paths (e.g. './components/Header.jsx' or '../utils/api.js'). NEVER prepend doubled area prefixes like 'frontend/frontend/...'.
"""

# Fields FrontendDev needs from the accumulated context (Design + FilePlanner).
# Architect modules, data_models, backend infrastructure, security details are
# not needed for implementing React components — dropping them saves ~3-5K tokens.
_FRONTEND_KEYS = frozenset({
    "project_name",
    "scale_profile",
    "tech_stack",
    "components",        # from Designer: component specs with shadcn_component, states
    "page_layouts",      # from Designer: page structure
    "user_flows",        # from Designer: navigation and state flows
    "design_system",     # from Designer: colors, fonts, spacing, breakpoints
    "frontend_files",    # from FilePlanner: which files belong to frontend area
    "api_endpoints",     # endpoint names/paths frontend must call
})

class FrontendPromptBuilder(PromptBuilder, SlimContextExtractor):
    """Advanced prompt builder for Frontend Developer stage.

    Uses SlimContextExtractor to pull only design-spec and frontend-file fields,
    saving ~65% of context tokens vs passing the full multi-artifact JSON.
    """

    def build(self, context: object | None = None) -> str:
        raw_content = self.get_raw_content(context)
        slim = self.extract(raw_content, _FRONTEND_KEYS)
        if slim:
            body = f"Frontend Prompt:\nDesign + file plan context (frontend-relevant fields):\n{slim}"
        else:
            body = f"Frontend Prompt:\nContext: {raw_content[:3000]}" if raw_content else "Frontend Prompt"
        return f"{_ROLE_BRIEFING}\n\n{body}"

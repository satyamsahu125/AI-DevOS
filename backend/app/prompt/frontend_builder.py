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

_MOBILE_ROLE_BRIEFING = """You are a Staff React Native Engineer implementing production-ready mobile apps using Expo SDK 51.

CRITICAL RULES — NEVER VIOLATE:
  1. NEVER use <div>, <span>, <button>, <input>, <form>, <a> — use RN primitives only
  2. NEVER use localStorage — use AsyncStorage from @react-native-async-storage/async-storage
  3. NEVER use window, document, or any browser API
  4. NEVER use CSS files or className without NativeWind
  5. NEVER use react-dom or ReactDOM
  6. Files go to project root (App.tsx) and src/ — NOT frontend/

REACT NATIVE PRIMITIVES (always use these):
  Layout:      View, ScrollView, FlatList, SectionList, SafeAreaView
  Text:        Text, TextInput
  Interaction: TouchableOpacity, Pressable, Switch, Slider
  Media:       Image, ImageBackground
  Overlay:     Modal, ActivityIndicator

NAVIGATION (React Navigation v6):
  import { useNavigation } from "@react-navigation/native"
  import { createNativeStackNavigator } from "@react-navigation/native-stack"
  import { createBottomTabNavigator } from "@react-navigation/bottom-tabs"
  navigation.navigate("ScreenName") — NEVER href or window.location

STYLING (NativeWind — Tailwind for RN):
  import { styled } from "nativewind"
  Use className prop exactly like Tailwind web BUT only RN-supported utilities
  Supported: flex, items-, justify-, p-, m-, text-, bg-, border-, rounded-, w-, h-, opacity-
  NOT supported: hover:, focus:, grid (use flex instead)

STORAGE:
  import AsyncStorage from "@react-native-async-storage/async-storage"
  await AsyncStorage.setItem("key", JSON.stringify(value))
  const raw = await AsyncStorage.getItem("key")

EXPO SDK 51 IMPORTS:
  import { StatusBar } from "expo-status-bar"
  import * as Font from "expo-font"
  import * as SplashScreen from "expo-splash-screen"
  import { useColorScheme } from "react-native"

FILE STRUCTURE (no frontend/ directory):
  App.tsx                    ← Expo entry point
  src/screens/ScreenName.tsx ← individual screens
  src/components/Widget.tsx  ← reusable components
  src/hooks/useHookName.ts   ← custom hooks
  src/storage/storeName.ts   ← AsyncStorage helpers
  src/navigation/index.tsx   ← navigator setup
  src/types/index.ts         ← shared TypeScript types
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
    Dispatches to _MOBILE_ROLE_BRIEFING for mobile_app project types.
    """

    def build(self, context: object | None = None) -> str:
        raw_content = self.get_raw_content(context)

        # Determine project type to pick the right role briefing
        project_type = "web_fullstack"
        try:
            import json as _json
            raw = raw_content or ""
            if isinstance(raw, str) and raw.strip().startswith("{"):
                parsed = _json.loads(raw)
                nfr = parsed.get("non_functional_requirements") or {}
                project_type = (
                    nfr.get("project_type")
                    or parsed.get("project_type")
                    or (parsed.get("tech_stack") or {}).get("project_type")
                    or "web_fullstack"
                ).lower()
        except Exception:
            pass

        role_briefing = _MOBILE_ROLE_BRIEFING if project_type == "mobile_app" else _ROLE_BRIEFING

        slim = self.extract(raw_content, _FRONTEND_KEYS)
        if slim:
            body = f"Frontend Prompt:\nDesign + file plan context (frontend-relevant fields):\n{slim}"
        else:
            body = f"Frontend Prompt:\nContext: {raw_content[:3000]}" if raw_content else "Frontend Prompt"
        return f"{role_briefing}\n\n{body}"

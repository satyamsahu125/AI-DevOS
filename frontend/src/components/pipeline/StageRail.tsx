import { motion, AnimatePresence } from "framer-motion"
import { STAGES, STAGE_LABELS, type StageName } from "../../lib/api"

const STAGE_ICONS: Record<StageName, string> = {
  DomainResearch:       "🔍",
  Clarifying:           "❓",
  StrategicReview:      "🎯",
  ProductOwner:         "📋",
  Architect:            "🏛",
  Designer:             "🎨",
  Security:             "🔒",
  SprintPlanning:       "🗓",
  ScrumMaster:          "🏃",
  FileStructurePlanner: "📁",
  BackendDeveloper:     "⚙️",
  FrontendDeveloper:    "💻",
  Integration:          "🔗",
  SprintDeploy:         "📦",
  SprintReview:         "🔎",
  QA:                   "🧪",
  BugAnalyst:           "🐛",
  DevOps:               "🚀",
  Document:             "📄",
  Retro:                "🔄",
}

// ── Color tokens (using aurora palette) ──────────────────────────────────────
const COLORS = {
  done:    { ring: "rgba(16,185,129,0.3)",  bg: "#10B981", text: "#34d399" },
  current: { ring: "rgba(124,58,237,0.4)",  bg: "#7C3AED", text: "#a78bfa" },
  failed:  { ring: "rgba(244,63,94,0.35)",  bg: "#F43F5E", text: "#fb7185" },
  pending: { ring: "rgba(255,255,255,0.08)", bg: "#27272a", text: "#52525b" },
}

// ── Node animation variants ───────────────────────────────────────────────────
const nodeVariant = {
  done: {
    scale: [1, 1.25, 1],
    transition: { duration: 0.45, ease: "easeOut" },
  },
  current: {
    scale: 1,
    transition: { type: "spring" as const, stiffness: 300, damping: 20 },
  },
  idle: { scale: 1 },
}

interface StageRailProps {
  completedStages: string[]
  currentStage: string | null
  failedStage: string | null
}

export function StageRail({ completedStages, currentStage, failedStage }: StageRailProps) {
  const completed = new Set(completedStages.map(s => s.toLowerCase()))

  return (
    <div className="flex items-center gap-0 overflow-x-auto scrollbar-none">
      {STAGES.map((stage, i) => {
        const key = stage.toLowerCase()
        const isCurrent = currentStage?.toLowerCase() === key
        const isDone = completed.has(key)
        const isFailed = failedStage?.toLowerCase() === key

        const colors =
          isFailed  ? COLORS.failed  :
          isDone    ? COLORS.done    :
          isCurrent ? COLORS.current :
                      COLORS.pending

        const stateKey = isFailed ? "done" : isDone ? "done" : isCurrent ? "current" : "idle"

        return (
          <div key={stage} className="flex items-center">
            {/* Stage node */}
            <div className="flex flex-col items-center gap-1 px-2">
              <motion.div
                animate={stateKey}
                variants={nodeVariant}
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  background: colors.bg,
                  boxShadow: `0 0 0 2px ${colors.ring}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  color: "#fff",
                  position: "relative",
                }}
                title={STAGE_LABELS[stage]}
              >
                {/* Pulse ring for current stage */}
                {isCurrent && (
                  <motion.span
                    style={{
                      position: "absolute",
                      inset: -3,
                      borderRadius: "50%",
                      border: `1.5px solid ${COLORS.current.bg}`,
                      opacity: 0,
                    }}
                    animate={{ opacity: [0, 0.6, 0], scale: [0.85, 1.3, 1.3] }}
                    transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
                  />
                )}

                <AnimatePresence mode="wait">
                  <motion.span
                    key={isFailed ? "fail" : isDone ? "done" : isCurrent ? "current" : "pending"}
                    initial={{ opacity: 0, scale: 0.6 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.6 }}
                    transition={{ duration: 0.2 }}
                  >
                    {isFailed ? "✗" : isDone ? "✓" : isCurrent ? STAGE_ICONS[stage] : String(i + 1)}
                  </motion.span>
                </AnimatePresence>
              </motion.div>

              <span style={{
                fontSize: 9,
                whiteSpace: "nowrap",
                color: colors.text,
                fontWeight: isCurrent ? 600 : 400,
                letterSpacing: "0.01em",
              }}>
                {STAGE_LABELS[stage]}
              </span>
            </div>

            {/* Connector with fill animation */}
            {i < STAGES.length - 1 && (
              <div style={{
                height: 1,
                width: 12,
                flexShrink: 0,
                background: "#27272a",
                position: "relative",
                overflow: "hidden",
              }}>
                <motion.div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background: COLORS.done.bg,
                    transformOrigin: "left",
                  }}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: isDone ? 1 : 0 }}
                  transition={{ duration: 0.3, ease: "easeOut", delay: isDone ? 0.1 : 0 }}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

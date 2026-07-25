import { motion, AnimatePresence } from "framer-motion"
import { CheckCircle2, Loader2, Circle, XCircle, ChevronDown } from "lucide-react"
import { useState } from "react"

export interface PipelineStage {
  name: string
  label: string
  status: "complete" | "processing" | "pending" | "failed" | string
  attempt?: number
}

interface PipelineViewProps {
  pipeline: PipelineStage[]
  agentLogs?: Record<string, string[]>
}

const stageIcons: Record<string, { icon: any; color: string; bg: string; spin?: boolean }> = {
  complete: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30" },
  processing: { icon: Loader2, color: "text-cyan-400", bg: "bg-cyan-500/10 border-cyan-500/30", spin: true },
  pending: { icon: Circle, color: "text-white/20", bg: "bg-white/5 border-white/10" },
  failed: { icon: XCircle, color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/30" },
}

export function PipelineView({ pipeline, agentLogs = {} }: PipelineViewProps) {
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <div className="space-y-3 p-4">
      {pipeline.map((stage, idx) => {
        const config = stageIcons[stage.status] || stageIcons.pending
        const Icon = config.icon
        const isExpanded = expanded === stage.name
        const logs = agentLogs[stage.name] || []

        return (
          <motion.div
            key={stage.name}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.05 }}
            className={`glass-card overflow-hidden transition-all duration-300 ${
              stage.status === "processing" ? "aurora-border" : ""
            }`}
          >
            {/* Stage header */}
            <button
              className="w-full flex items-center gap-3 p-4 text-left cursor-pointer"
              onClick={() => setExpanded(isExpanded ? null : stage.name)}
            >
              {/* Status icon */}
              <div className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${config.bg}`}>
                <Icon size={14} className={`${config.color} ${config.spin ? "animate-spin" : ""}`} />
              </div>

              {/* Stage info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-white/90">{stage.label}</span>
                  {stage.status === "complete" && (
                    <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} className="text-xs text-emerald-400/60">
                      ✓ approved on attempt {stage.attempt || 1}
                    </motion.span>
                  )}
                  {stage.status === "processing" && (
                    <span className="text-xs text-cyan-400/60 animate-pulse">generating...</span>
                  )}
                </div>
              </div>

              {/* Expand chevron */}
              {logs.length > 0 && (
                <motion.div animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronDown size={14} className="text-white/30" />
                </motion.div>
              )}
            </button>

            {/* Expandable logs */}
            <AnimatePresence>
              {isExpanded && logs.length > 0 && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 pt-0 border-t border-white/5">
                    <div className="space-y-1.5 mt-3">
                      {logs.map((log, i) => (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.05 }}
                          className="flex items-start gap-2 text-xs"
                        >
                          <span className="text-white/20 mt-0.5">›</span>
                          <span className="text-white/50 font-mono">{log}</span>
                        </motion.div>
                      ))}
                      {stage.status === "processing" && (
                        <div className="flex items-center gap-2 text-xs mt-2">
                          <span className="text-white/20">›</span>
                          <span className="text-cyan-400/70 font-mono animate-pulse">
                            generating with AI model...
                          </span>
                          <div className="flex gap-1">
                            {[0, 1, 2].map((i) => (
                              <motion.div
                                key={i}
                                animate={{ opacity: [0.3, 1, 0.3] }}
                                transition={{
                                  duration: 1,
                                  repeat: Infinity,
                                  delay: i * 0.2,
                                }}
                                className="w-1 h-1 rounded-full bg-cyan-400"
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )
      })}
    </div>
  )
}

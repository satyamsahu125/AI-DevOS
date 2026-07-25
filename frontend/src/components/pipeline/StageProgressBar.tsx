import { motion } from "framer-motion"
import { CheckCircle2, Circle, Loader2 } from "lucide-react"
import type { PipelineStage } from "./PipelineView"

interface StageProgressBarProps {
  stages: PipelineStage[]
  currentStage?: string | null
}

export function StageProgressBar({ stages, currentStage }: StageProgressBarProps) {
  return (
    <div className="flex items-center gap-0 overflow-x-auto py-3 px-4 scrollbar-none">
      {stages.map((stage, i) => {
        const isComplete = stage.status === "complete"
        const isActive = stage.status === "processing" || stage.name === currentStage

        return (
          <div key={stage.name} className="flex items-center">
            {/* Stage node */}
            <div className="flex flex-col items-center gap-1.5 px-2">
              <motion.div
                whileHover={{ scale: 1.15 }}
                className={`relative w-7 h-7 rounded-full flex items-center justify-center border transition-all duration-300 ${
                  isComplete
                    ? "bg-emerald-500/20 border-emerald-500/50"
                    : isActive
                    ? "bg-violet-500/20 border-violet-500/60 shadow-glow-purple animate-pulse-slow"
                    : "bg-white/5 border-white/10"
                }`}
              >
                {isComplete ? (
                  <CheckCircle2 size={12} className="text-emerald-400" />
                ) : isActive ? (
                  <Loader2 size={12} className="text-violet-400 animate-spin" />
                ) : (
                  <Circle size={10} className="text-white/20" />
                )}
              </motion.div>

              <span
                className={`text-[10px] font-medium whitespace-nowrap max-w-[70px] text-center leading-tight ${
                  isComplete ? "text-emerald-400/70" : isActive ? "text-violet-300" : "text-white/25"
                }`}
              >
                {stage.label}
              </span>
            </div>

            {/* Connector line */}
            {i < stages.length - 1 && (
              <div className="w-6 h-px flex-shrink-0 -mt-4">
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: isComplete ? 1 : 0 }}
                  transition={{ duration: 0.4, delay: 0.2 }}
                  className="h-full bg-emerald-500/40 origin-left"
                />
                {!isComplete && <div className="h-full bg-white/10" />}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

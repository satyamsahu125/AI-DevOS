import { motion } from "framer-motion"
import { ArrowRight, CheckCircle2, Loader2, Clock, AlertCircle } from "lucide-react"

export interface ProjectCardData {
  project_id: string
  name: string
  description?: string
  status?: string
  state?: string
  current_stage?: string
  stages_completed?: string[]
}

interface ProjectCardProps {
  project: ProjectCardData
  onClick?: () => void
}

const stateConfig: Record<string, { color: string; label: string; icon: any }> = {
  done: { color: "emerald", label: "Complete", icon: CheckCircle2 },
  sprint_in_progress: { color: "cyan", label: "Building", icon: Loader2 },
  design_review_pending: { color: "amber", label: "Review", icon: Clock },
  failed: { color: "rose", label: "Failed", icon: AlertCircle },
}

export function ProjectCard({ project, onClick }: ProjectCardProps) {
  const stateKey = project.state || "active"
  const config = stateConfig[stateKey] || { color: "violet", label: "Active", icon: Loader2 }
  const Icon = config.icon
  const progress = project.stages_completed?.length || 0
  const total = 12
  const pct = Math.min(100, Math.round((progress / total) * 100))

  return (
    <motion.div
      whileHover={{ y: -3, scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      onClick={onClick}
      className="glass-card-hover p-5 cursor-pointer group"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-semibold text-white/90 text-sm group-hover:text-white transition-colors">
            {project.name}
          </h3>
          <p className="text-white/40 text-xs mt-0.5 line-clamp-1">
            {project.description || "No description"}
          </p>
        </div>
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${
            config.color === "emerald"
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              : config.color === "cyan"
              ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400"
              : config.color === "amber"
              ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
              : config.color === "rose"
              ? "bg-rose-500/10 border-rose-500/20 text-rose-400"
              : "bg-violet-500/10 border-violet-500/20 text-violet-400"
          }`}
        >
          {Icon && (
            <Icon
              size={11}
              className={`${project.state === "sprint_in_progress" ? "animate-spin" : ""}`}
            />
          )}
          <span>{config.label}</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-white/30 mb-1.5">
          <span>Stage {progress}/{total}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-1 bg-white/5 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="h-full rounded-full bg-aurora"
          />
        </div>
      </div>

      {/* Current stage */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-white/30">
          {project.current_stage ? `↳ ${project.current_stage}` : "Not started"}
        </span>
        <ArrowRight
          size={14}
          className="text-white/20 group-hover:text-violet-400 group-hover:translate-x-1 transition-all duration-200"
        />
      </div>
    </motion.div>
  )
}

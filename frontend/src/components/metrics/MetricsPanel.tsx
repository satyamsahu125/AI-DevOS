import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Zap, Clock, Hash, DollarSign, TrendingUp, AlertCircle } from "lucide-react"

export function MetricsPanel({ projectId }: { projectId: string }) {
  const [metrics, setMetrics] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    fetch(`/api/projects/${projectId}/metrics`)
      .then((r) => r.json())
      .then((data) => {
        setMetrics(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [projectId])

  if (loading) {
    return (
      <div className="p-4 space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 glass-card animate-pulse rounded-xl border border-white/5" />
        ))}
      </div>
    )
  }

  if (!metrics || metrics.total_llm_calls === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-center p-4">
        <TrendingUp size={24} className="text-white/15 mb-3" />
        <p className="text-sm text-white/40">Metrics appear after pipeline runs</p>
      </div>
    )
  }

  const stats = [
    {
      icon: Hash,
      label: "Total LLM Calls",
      value: metrics.total_llm_calls,
      color: "text-violet-400",
    },
    {
      icon: Zap,
      label: "Total Tokens",
      value: metrics.total_tokens?.toLocaleString() || 0,
      color: "text-cyan-400",
    },
    {
      icon: Clock,
      label: "Pipeline Time",
      value: `${metrics.total_latency_seconds}s`,
      color: "text-amber-400",
    },
    {
      icon: DollarSign,
      label: "Estimated Cost",
      value: metrics.estimated_cost_usd === 0 ? "Free (local)" : `$${metrics.estimated_cost_usd}`,
      color: "text-emerald-400",
    },
  ]

  return (
    <div className="p-4 space-y-4">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card p-3 rounded-xl border border-white/10"
            >
              <div className="flex items-center gap-1.5 mb-1">
                <Icon size={12} className={stat.color} />
                <span className="text-xs text-white/40">{stat.label}</span>
              </div>
              <p className={`text-lg font-bold ${stat.color}`}>{stat.value}</p>
            </motion.div>
          )
        })}
      </div>

      {/* Per-stage breakdown */}
      <div>
        <p className="text-xs text-white/30 uppercase tracking-wider mb-2 font-mono">
          Per Stage Breakdown
        </p>
        <div className="space-y-2">
          {metrics.stages?.map((stage: any) => {
            const retried = stage.retries > 0
            const maxTokens = Math.max(...metrics.stages.map((s: any) => s.total_tokens))
            const width = maxTokens > 0 ? (stage.total_tokens / maxTokens) * 100 : 0

            return (
              <div key={stage.stage} className="glass-card p-3 rounded-lg border border-white/10">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white/80 font-medium capitalize">
                      {stage.stage.replace(/_/g, " ")}
                    </span>
                    {retried && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">
                        {stage.retries} retry
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-white/40 font-mono">
                    <span>{stage.total_tokens.toLocaleString()} tokens</span>
                    <span>{Math.round(stage.avg_latency_ms / 1000)}s</span>
                  </div>
                </div>
                {/* Token bar */}
                <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${width}%` }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="h-full bg-indigo-500 rounded-full"
                  />
                </div>
                {stage.success_rate < 1 && (
                  <p className="text-xs text-rose-400/60 mt-1 flex items-center gap-1">
                    <AlertCircle size={10} />
                    {Math.round((1 - stage.success_rate) * 100)}% failure rate
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { TrendingUp, TrendingDown, Minus, Brain, Lightbulb, Star } from "lucide-react"

export function MemoryPage() {
  const [performance, setPerformance] = useState<any>(null)
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [insights, setInsights] = useState<any>(null)

  useEffect(() => {
    fetch("/api/learning/performance")
      .then((r) => r.json())
      .then(setPerformance)
      .catch(() => setPerformance(null))
  }, [])

  useEffect(() => {
    if (selectedStage) {
      fetch(`/api/learning/insights/${selectedStage}`)
        .then((r) => r.json())
        .then(setInsights)
        .catch(() => setInsights(null))
    }
  }, [selectedStage])

  const scores = performance?.scores || []

  return (
    <div className="max-w-4xl mx-auto p-6 overflow-y-auto h-full">
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-1">
          <Brain size={20} className="text-violet-400" />
          <h1 className="text-xl font-bold text-white/90">Learning System</h1>
        </div>
        <p className="text-white/40 text-sm">
          AI DevOS learns from every project it runs. Performance improves automatically over time.
        </p>
      </div>

      {/* Agent Performance Grid */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-white/50 uppercase tracking-wider mb-4">
          Agent Performance
        </h2>

        {scores.length === 0 ? (
          <div className="glass-card p-8 text-center border border-white/10 rounded-xl">
            <TrendingUp size={32} className="text-white/15 mx-auto mb-3" />
            <p className="text-white/40 text-sm">
              Performance data appears after running projects.
              <br />
              The more projects you run, the smarter AI DevOS becomes.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {scores.map((score: any) => {
              const Icon =
                score.score >= 0.85
                  ? TrendingUp
                  : score.score >= 0.5
                  ? Minus
                  : TrendingDown
              const isExcellent = score.score >= 0.85
              const isGood = score.score >= 0.5

              return (
                <motion.button
                  key={score.stage}
                  whileHover={{ y: -2 }}
                  onClick={() =>
                    setSelectedStage(selectedStage === score.stage ? null : score.stage)
                  }
                  className={`glass-card p-4 text-left transition-all duration-200 rounded-xl border ${
                    selectedStage === score.stage
                      ? "border-violet-500/40 bg-violet-500/5"
                      : "border-white/10 hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-white/80 capitalize">
                      {score.stage.replace(/_/g, " ")}
                    </span>
                    <div
                      className={`flex items-center gap-1 text-xs font-semibold ${
                        isExcellent
                          ? "text-emerald-400"
                          : isGood
                          ? "text-amber-400"
                          : "text-rose-400"
                      }`}
                    >
                      <Icon size={12} />
                      {score.quality}
                    </div>
                  </div>

                  {/* Score bar */}
                  <div className="h-1.5 bg-white/5 rounded-full overflow-hidden mb-2">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(score.score || 0) * 100}%` }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                      className={`h-full rounded-full ${
                        isExcellent
                          ? "bg-emerald-400"
                          : isGood
                          ? "bg-amber-400"
                          : "bg-rose-400"
                      }`}
                    />
                  </div>

                  <div className="flex justify-between text-xs text-white/30 font-mono">
                    <span>Score: {Math.round((score.score || 0) * 100)}%</span>
                    <span>
                      {score.total_runs} runs · {score.avg_retries?.toFixed(1)} retries
                    </span>
                  </div>
                </motion.button>
              )
            })}
          </div>
        )}
      </div>

      {/* Stage insights */}
      {selectedStage && insights && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-5 rounded-xl border border-white/10 bg-slate-900/60"
        >
          <div className="flex items-center gap-2 mb-4">
            <Lightbulb size={16} className="text-amber-400" />
            <h3 className="font-medium text-white/90 text-sm capitalize">
              Insights: {selectedStage.replace(/_/g, " ")}
            </h3>
            <span className="text-xs text-white/30 ml-auto font-mono">
              {insights.lessons_analyzed || 0} lessons analyzed
            </span>
          </div>

          {insights.insights?.length > 0 ? (
            <div className="space-y-2 mb-4">
              {insights.insights.map((insight: string, i: number) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <Star size={12} className="text-amber-400/60 mt-0.5 flex-shrink-0" />
                  <p className="text-white/60">{insight}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/40 text-sm">
              No insights yet — run more projects to build pattern data.
            </p>
          )}

          {insights.what_works?.[0] && (
            <div className="mt-3">
              <p className="text-xs text-emerald-400 mb-1 font-medium">What works:</p>
              <p className="text-xs text-white/50">{insights.what_works[0]}</p>
            </div>
          )}

          {insights.common_failures?.[0] && (
            <div className="mt-3">
              <p className="text-xs text-rose-400 mb-1 font-medium">Common failures:</p>
              <p className="text-xs text-white/50">{insights.common_failures[0]}</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}

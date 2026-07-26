import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  GitBranch,
  CheckCircle2,
  XCircle,
  RefreshCw,
  ArrowRight,
  Loader2,
} from "lucide-react"

interface RequirementChangePanelProps {
  projectId: string
  onChangeApplied?: () => void
}

export function RequirementChangePanel({
  projectId,
  onChangeApplied,
}: RequirementChangePanelProps) {
  const [step, setStep] = useState<
    "input" | "analyzing" | "review" | "applying" | "done"
  >("input")
  const [description, setDescription] = useState("")
  const [comment, setComment] = useState("")
  const [analysis, setAnalysis] = useState<any>(null)

  const submitChange = async () => {
    if (!description.trim()) return
    setStep("analyzing")
    try {
      const res = await fetch(`/api/workflow/${projectId}/change`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description }),
      })
      const data = await res.json()
      setAnalysis(data)
      setStep("review")
    } catch {
      setStep("input")
    }
  }

  const confirmChange = async () => {
    setStep("applying")
    try {
      await fetch(`/api/workflow/${projectId}/change/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          change_id: analysis.change_id,
          confirmed: true,
          comment,
        }),
      })
      // Resume pipeline
      await fetch(`/api/workflow/${projectId}/continue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request: description,
        }),
      })
      setStep("done")
      onChangeApplied?.()
    } catch {
      setStep("review")
    }
  }

  const cancelChange = async () => {
    if (analysis) {
      await fetch(`/api/workflow/${projectId}/change/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          change_id: analysis.change_id,
        }),
      })
    }
    setStep("input")
    setDescription("")
    setAnalysis(null)
  }

  return (
    <div className="glass-card p-5 mx-4 my-3">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <GitBranch size={16} className="text-violet-400" />
        <h3 className="text-sm font-semibold text-white/90">
          Change Requirements
        </h3>
        <span className="text-xs text-white/30 ml-auto">
          Only affected stages will re-run
        </span>
      </div>

      <AnimatePresence mode="wait">
        {/* STEP: Input */}
        {step === "input" && (
          <motion.div
            key="input"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={`Describe what you want to change...

Examples:
  • Add dark mode support
  • Remove the payment integration
  • Change the user profile page to show analytics
  • Add real-time notifications`}
              rows={4}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm text-white/80 placeholder:text-white/25 outline-none focus:border-violet-500/40 resize-none transition-colors mb-3"
            />
            <button
              onClick={submitChange}
              disabled={!description.trim()}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-violet-500/20 border border-violet-500/30 text-violet-300 hover:bg-violet-500/30 transition-all text-sm font-medium disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
            >
              <ArrowRight size={14} />
              Analyze Impact
            </button>
          </motion.div>
        )}

        {/* STEP: Analyzing */}
        {step === "analyzing" && (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center py-6 gap-3"
          >
            <Loader2 size={24} className="text-violet-400 animate-spin" />
            <p className="text-sm text-white/50">
              Analyzing which stages are affected...
            </p>
          </motion.div>
        )}

        {/* STEP: Review impact */}
        {step === "review" && analysis && (
          <motion.div
            key="review"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            {/* Explanation */}
            <div className="glass-card p-3 rounded-lg mb-4">
              <p className="text-xs text-white/60">{analysis.explanation}</p>
            </div>

            {/* Affected stages */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <p className="text-xs text-rose-400 mb-2 flex items-center gap-1">
                  <RefreshCw size={10} />
                  Will re-run ({analysis.affected_stages?.length || 0})
                </p>
                {analysis.affected_stages?.map((s: string) => (
                  <div
                    key={s}
                    className="text-xs text-white/50 flex items-center gap-1.5 mb-1"
                  >
                    <XCircle size={10} className="text-rose-400/60" />
                    {s.replace(/_/g, " ")}
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs text-emerald-400 mb-2 flex items-center gap-1">
                  <CheckCircle2 size={10} />
                  Preserved ({analysis.safe_stages?.length || 0})
                </p>
                {analysis.safe_stages?.map((s: string) => (
                  <div
                    key={s}
                    className="text-xs text-white/50 flex items-center gap-1.5 mb-1"
                  >
                    <CheckCircle2 size={10} className="text-emerald-400/60" />
                    {s.replace(/_/g, " ")}
                  </div>
                ))}
              </div>
            </div>

            {/* Optional extra comment */}
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Optional: any extra context..."
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/70 placeholder:text-white/25 outline-none focus:border-violet-500/40 mb-3 transition-colors"
            />

            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={cancelChange}
                className="flex-1 py-2 rounded-lg text-sm text-white/40 hover:text-white/60 border border-white/10 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmChange}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm bg-violet-500/20 border border-violet-500/30 text-violet-300 hover:bg-violet-500/30 transition-all font-medium cursor-pointer"
              >
                <RefreshCw size={13} />
                Apply & Re-run
              </button>
            </div>
          </motion.div>
        )}

        {/* STEP: Applying */}
        {step === "applying" && (
          <motion.div
            key="applying"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center py-6 gap-3"
          >
            <Loader2 size={24} className="text-violet-400 animate-spin" />
            <p className="text-sm text-white/50">
              Applying changes and resuming pipeline...
            </p>
          </motion.div>
        )}

        {/* STEP: Done */}
        {step === "done" && (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center py-4 gap-2"
          >
            <CheckCircle2 size={24} className="text-emerald-400" />
            <p className="text-sm text-white/70">
              Changes applied. Pipeline resuming...
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

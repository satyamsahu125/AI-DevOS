import { useState } from "react"
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react"
import { motion } from "framer-motion"

interface Finding {
  tier?: string
  severity?: string
  description?: string
  title?: string
}

interface ReviewerDecision {
  approved?: boolean
  findings?: Finding[]
}

interface ApprovalPanelProps {
  projectId: string
  stage: string
  reviewerDecision?: ReviewerDecision
  artifactPreview?: string
  onDecision: (decision: "approved" | "rejected") => void
}

export function ApprovalPanel({
  projectId,
  stage,
  reviewerDecision,
  artifactPreview,
  onDecision,
}: ApprovalPanelProps) {
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const handleApprove = async () => {
    setSubmitting(true)
    try {
      await fetch(`/api/workflow/${projectId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage,
          approved: true,
          comment: "Operator approved",
        }),
      })
      onDecision("approved")
    } catch {
      // fallback decision
      onDecision("approved")
    }
    setSubmitting(false)
  }

  const handleReject = async () => {
    if (!comment.trim()) return
    setSubmitting(true)
    try {
      await fetch(`/api/workflow/${projectId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage,
          approved: false,
          comment,
        }),
      })
      onDecision("rejected")
    } catch {
      onDecision("rejected")
    }
    setSubmitting(false)
  }

  const findings = reviewerDecision?.findings || []
  const askHuman = findings.filter((f) => f.tier === "ASK_HUMAN" || f.severity === "CRITICAL")

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card aurora-border p-6 mx-4 my-4 rounded-2xl bg-slate-900/80 border border-white/10 shadow-2xl"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center shrink-0">
          <AlertTriangle size={18} className="text-amber-400" />
        </div>
        <div>
          <h3 className="font-semibold text-white/90 text-sm">
            Human Approval Required
          </h3>
          <p className="text-xs text-white/40">
            {stage} stage completed
          </p>
        </div>
      </div>

      {/* Reviewer findings */}
      {askHuman.length > 0 && (
        <div className="mb-4 glass-card p-3 rounded-xl bg-amber-500/5 border border-amber-500/20">
          <p className="text-xs font-semibold text-amber-400 mb-2">
            Reviewer flagged for human review:
          </p>
          {askHuman.map((f, i) => (
            <p key={i} className="text-xs text-white/70 mb-1">
              · {f.description || f.title}
            </p>
          ))}
        </div>
      )}

      {/* Artifact preview */}
      {artifactPreview && (
        <div className="glass-card p-3.5 rounded-xl mb-4 bg-slate-950/60 border border-white/5">
          <p className="text-xs text-white/40 mb-2 font-medium">
            Artifact preview:
          </p>
          <p className="text-xs text-white/70 font-mono leading-relaxed line-clamp-4 whitespace-pre-wrap">
            {artifactPreview}
          </p>
        </div>
      )}

      {/* Actions */}
      {!rejecting ? (
        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            disabled={submitting}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30 transition-all text-sm font-medium disabled:opacity-40 cursor-pointer shadow-sm"
          >
            <CheckCircle2 size={16} />
            Approve &amp; Continue
          </button>
          <button
            onClick={() => setRejecting(true)}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 transition-all text-sm font-medium cursor-pointer"
          >
            <XCircle size={16} />
            Reject &amp; Retry
          </button>
        </div>
      ) : (
        <div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What should be changed or improved? The agent will retry with your feedback..."
            rows={3}
            className="w-full bg-slate-950/80 border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white/90 placeholder:text-white/30 outline-none focus:border-rose-500/40 resize-none mb-3 transition-colors font-sans"
          />
          <div className="flex gap-2">
            <button
              onClick={() => setRejecting(false)}
              className="flex-1 py-2 rounded-xl text-xs font-medium text-white/50 hover:text-white/80 border border-white/10 hover:bg-white/5 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleReject}
              disabled={!comment.trim() || submitting}
              className="flex-1 py-2 rounded-xl text-xs font-medium bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 transition-all border border-rose-500/30 disabled:opacity-40 cursor-pointer"
            >
              Send Feedback
            </button>
          </div>
        </div>
      )}
    </motion.div>
  )
}

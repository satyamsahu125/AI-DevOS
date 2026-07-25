import { Check, Loader2, X, Sparkles, Layers, ArrowRight } from "lucide-react"

import { STAGES, STAGE_LABELS, type WorkflowStatus } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

type StageState = "waiting" | "running" | "completed" | "failed"

function stageState(stage: string, status: WorkflowStatus | null): StageState {
  if (!status) return "waiting"
  if (status.completed_stages.includes(stage)) return "completed"
  if (status.failed_stage === stage) return "failed"
  if (status.current_stage === stage && status.status === "running") return "running"
  return "waiting"
}

const STATE_STYLES: Record<StageState, string> = {
  waiting: "border-white/5 bg-slate-900/40 text-slate-500",
  running: "border-indigo-500/60 bg-indigo-600/20 text-indigo-300 shadow-[0_0_15px_rgba(99,102,241,0.3)] font-semibold scale-105",
  completed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400 font-medium",
  failed: "border-rose-500/50 bg-rose-500/10 text-rose-400 font-medium",
}

interface WorkflowPanelProps {
  status: WorkflowStatus | null
  onOpenDesignReview?: () => void
}

export function WorkflowPanel({ status, onOpenDesignReview }: WorkflowPanelProps) {
  const st = status?.state ? String(status.state).toLowerCase() : ""
  const requiresAction = Boolean(
    status?.requires_user_action ||
    st.includes("design_review") ||
    st === "design_ready" ||
    st === "awaiting_human" ||
    st === "human_action_required"
  )

  return (
    <div className="flex flex-col gap-3 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl px-6 py-3.5 shadow-lg">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Layers className="size-4 text-indigo-400 animate-pulse" />
            <h2 className="text-xs font-bold tracking-wider text-slate-200 uppercase">12-Stage Agent Pipeline</h2>
          </div>
          {status?.sprint_name && (
            <span className="rounded-full bg-indigo-950/80 border border-indigo-500/30 px-3 py-0.5 text-[11px] font-mono font-medium text-indigo-300 shadow-sm">
              {status.sprint_name} &middot; {status.sprint_progress}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {requiresAction && onOpenDesignReview && (
            <Button
              size="sm"
              variant="default"
              className="h-7 text-xs bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 hover:from-amber-400 hover:to-amber-500 font-bold shadow-[0_0_15px_rgba(245,158,11,0.4)] animate-bounce"
              onClick={onOpenDesignReview}
            >
              <Sparkles className="mr-1.5 size-3.5" /> Action Required: Review & Approve
            </Button>
          )}

          {status && (
            <div className="flex items-center gap-2">
              <div className="w-28 bg-slate-900 rounded-full h-1.5 overflow-hidden border border-white/5">
                <div
                  className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full transition-all duration-500 rounded-full"
                  style={{ width: `${status.progress_percent}%` }}
                />
              </div>
              <span className="text-xs font-mono text-slate-400">
                {status.completed_stages.length}/{status.total_stages} ({status.progress_percent}%)
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Stage Node Pipeline Track */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {STAGES.map((stage, index) => {
          const state = stageState(stage, status)
          return (
            <div key={stage} className="flex items-center gap-1.5">
              <div
                className={cn(
                  "flex min-w-28 flex-col items-center gap-1 rounded-xl border px-3 py-1.5 text-center transition-all duration-300 backdrop-blur-md",
                  STATE_STYLES[state],
                )}
                title={STAGE_LABELS[stage]}
              >
                <div className="flex items-center gap-1.5">
                  {state === "running" && <Loader2 className="size-3 animate-spin text-indigo-400" />}
                  {state === "completed" && <Check className="size-3 text-emerald-400" />}
                  {state === "failed" && <X className="size-3 text-rose-400" />}
                  <span className="text-[11px] whitespace-nowrap">{STAGE_LABELS[stage]}</span>
                </div>
              </div>
              {index < STAGES.length - 1 && (
                <ArrowRight className={cn("size-3 shrink-0 text-slate-700", state === "completed" && "text-emerald-500/60")} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

import { Check, Loader2, X } from "lucide-react"

import { STAGES, STAGE_LABELS, type WorkflowStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

type StageState = "waiting" | "running" | "completed" | "failed"

function stageState(stage: string, status: WorkflowStatus | null): StageState {
  if (!status) return "waiting"
  if (status.completed_stages.includes(stage)) return "completed"
  if (status.failed_stage === stage) return "failed"
  if (status.current_stage === stage && status.status === "running") return "running"
  return "waiting"
}

const STATE_STYLES: Record<StageState, string> = {
  waiting: "border-border bg-card text-muted-foreground",
  running: "border-primary/60 bg-primary/10 text-primary",
  completed: "border-success/50 bg-success/10 text-success",
  failed: "border-destructive/50 bg-destructive/10 text-destructive",
}

export function WorkflowPanel({ status }: { status: WorkflowStatus | null }) {
  return (
    <div className="flex flex-col gap-3 border-b border-border bg-card/30 px-6 py-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Pipeline</h2>
        {status && (
          <span className="text-xs text-muted-foreground">
            {status.completed_stages.length}/{status.total_stages} stages &middot; {status.progress_percent}%
          </span>
        )}
      </div>
      <div className="flex items-center gap-1 overflow-x-auto pb-1">
        {STAGES.map((stage, index) => {
          const state = stageState(stage, status)
          return (
            <div key={stage} className="flex items-center gap-1">
              <div
                className={cn(
                  "flex min-w-28 flex-col items-center gap-1 rounded-lg border px-2.5 py-2 text-center transition-colors",
                  STATE_STYLES[state],
                )}
                title={STAGE_LABELS[stage]}
              >
                <div className="flex items-center gap-1">
                  {state === "running" && <Loader2 className="size-3 animate-spin" />}
                  {state === "completed" && <Check className="size-3" />}
                  {state === "failed" && <X className="size-3" />}
                  <span className="text-[11px] font-medium whitespace-nowrap">{STAGE_LABELS[stage]}</span>
                </div>
              </div>
              {index < STAGES.length - 1 && <div className="h-px w-3 shrink-0 bg-border" />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

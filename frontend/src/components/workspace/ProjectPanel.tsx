import { useState } from "react"
import { AlertTriangle, Loader2, Play, Square } from "lucide-react"

import { STAGE_LABELS, type ProjectDetail, type WorkflowStatus } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const STATUS_BADGE_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  failed: "destructive",
  complete: "success",
  running: "warning",
  stopped: "muted",
  paused: "muted",
  not_started: "muted",
}

interface ProjectPanelProps {
  project: ProjectDetail
  status: WorkflowStatus | null
  onStartBuild: (request: string) => void
  onStopBuild: () => void
  starting: boolean
  stopping: boolean
}

export function ProjectPanel({ project, status, onStartBuild, onStopBuild, starting, stopping }: ProjectPanelProps) {
  const [draft, setDraft] = useState(project.description)
  const isRunning = status?.status === "running"
  const canStart = status?.status !== "running"

  return (
    <div className="flex flex-col gap-3 border-b border-border p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold">{project.name}</h1>
          <p className="text-xs text-muted-foreground">
            {status?.current_stage ? STAGE_LABELS[status.current_stage as keyof typeof STAGE_LABELS] ?? status.current_stage : "Not started"}
          </p>
        </div>
        <Badge variant={STATUS_BADGE_VARIANT[status?.status ?? "not_started"]}>
          {status?.status ?? "not_started"}
        </Badge>
      </div>

      <div className="rounded-lg border border-border bg-card/40 p-3">
        <p className="mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Original request</p>
        <p className="text-xs">{project.description}</p>
      </div>

      <Textarea
        rows={3}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Describe what you want built…"
        disabled={isRunning}
        className="text-xs"
      />

      <div className="flex items-center justify-between gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button variant="outline" size="sm" disabled={!isRunning || stopping} onClick={onStopBuild}>
                {stopping ? <Loader2 className="size-3.5 animate-spin" /> : <Square className="size-3.5" />}
                Stop
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            Stops at the next checkpoint (between retry attempts or stages) -- it can't interrupt a single
            in-flight model call, since that's a blocking request to the LLM provider.
          </TooltipContent>
        </Tooltip>

        <Button size="sm" className="flex-1" onClick={() => onStartBuild(draft)} disabled={!canStart || starting || !draft.trim()}>
          {starting ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
          {status && status.completed_stages.length > 0 && status.status !== "complete" ? "Resume Build" : "Start Build"}
        </Button>
      </div>

      {isRunning && (
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" /> Build running…
        </span>
      )}

      {status?.failed_stage && (
        <p className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertTriangle className="size-3.5 shrink-0" />
          {STAGE_LABELS[status.failed_stage as keyof typeof STAGE_LABELS] ?? status.failed_stage} failed after all
          retries. Use "Retry stage" in Chat, or Resume Build to pick up from the next incomplete stage.
        </p>
      )}
    </div>
  )
}

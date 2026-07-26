import { useEffect, useState } from "react"
import { AlertTriangle, Loader2, Play, Square, Trash2, Coins, Sparkles } from "lucide-react"

import { STAGE_LABELS, api, type CostSummary, type ProjectDetail, type WorkflowStatus } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { RequirementChangePanel } from "@/components/changes/RequirementChangePanel"

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
  onDeleteProject?: () => void
  onOpenDesignReview?: () => void
  onChangeApplied?: () => void
  starting: boolean
  stopping: boolean
}

export function ProjectPanel({
  project,
  status,
  onStartBuild,
  onStopBuild,
  onDeleteProject,
  onOpenDesignReview,
  onChangeApplied,
  starting,
  stopping,
}: ProjectPanelProps) {
  const [draft, setDraft] = useState(project.description)
  const [cost, setCost] = useState<CostSummary | null>(null)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const isRunning = status?.status === "running"
  const canStart = status?.status !== "running"
  const requiresDesignReview = Boolean(
    status?.requires_user_action ||
    status?.state?.toLowerCase().includes("design_review") ||
    status?.state?.toLowerCase() === "design_ready" ||
    status?.state?.toLowerCase() === "awaiting_human" ||
    status?.state?.toLowerCase() === "human_action_required"
  )

  useEffect(() => {
    if (project?.project_id) {
      api.getCost(project.project_id).then(setCost).catch(() => setCost(null))
    }
  }, [project?.project_id, status?.completed_stages.length])

  async function handleDelete() {
    if (!project?.project_id) return
    setDeleting(true)
    try {
      await api.deleteProject(project.project_id)
      setDeleteConfirmOpen(false)
      if (onDeleteProject) onDeleteProject()
    } catch {
      setDeleting(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-b border-border p-4 bg-card/20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold truncate max-w-[200px]">{project.name}</h1>
          <p className="text-xs text-muted-foreground">
            {status?.current_stage
              ? STAGE_LABELS[status.current_stage as keyof typeof STAGE_LABELS] ?? status.current_stage
              : "Not started"}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Badge variant={STATUS_BADGE_VARIANT[status?.status ?? "not_started"]}>
            {status?.status ?? "not_started"}
          </Badge>
          <Button
            size="icon"
            variant="ghost"
            className="size-7 text-muted-foreground hover:text-destructive"
            onClick={() => setDeleteConfirmOpen(true)}
            title="Delete Project"
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card/40 p-3">
        <p className="mb-1 text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Original request</p>
        <p className="text-xs text-foreground/90">{project.description}</p>
      </div>

      {cost && (cost.prompt_tokens > 0 || cost.calls > 0) && (
        <div className="flex items-center justify-between rounded-lg border border-border/80 bg-accent/30 px-3 py-2 text-[11px] text-muted-foreground font-mono">
          <span className="flex items-center gap-1">
            <Coins className="size-3.5 text-amber-400" />
            {cost.calls} LLM Calls
          </span>
          <span>
            {cost.total_tokens.toLocaleString()} Tokens &middot; {(cost.total_latency_ms / 1000).toFixed(1)}s
          </span>
        </div>
      )}

      {requiresDesignReview && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 flex flex-col gap-2">
          <p className="text-xs text-amber-200 flex items-center gap-1.5 font-medium">
            <Sparkles className="size-3.5 text-amber-400" /> Design Review Ready
          </p>
          <p className="text-[11px] text-muted-foreground">
            Architect & Designer stages completed. Review the design spec to continue sprint planning.
          </p>
          {onOpenDesignReview && (
            <Button size="sm" className="bg-amber-500 text-black hover:bg-amber-400 text-xs h-7" onClick={onOpenDesignReview}>
              Review & Approve Design
            </Button>
          )}
        </div>
      )}

      <Textarea
        rows={2}
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
            Stops at the next checkpoint between stages.
          </TooltipContent>
        </Tooltip>

        <Button size="sm" className="flex-1" onClick={() => onStartBuild(draft)} disabled={!canStart || starting || !draft.trim()}>
          {starting ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
          {status && status.completed_stages.length > 0 && status.status !== "complete" ? "Resume Build" : "Start Build"}
        </Button>
      </div>

      {isRunning && (
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground animate-pulse">
          <Loader2 className="size-3 animate-spin text-primary" /> Multi-Agent AI Pipeline in progress…
        </span>
      )}

      {status?.failed_stage && (
        <p className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertTriangle className="size-3.5 shrink-0" />
          {STAGE_LABELS[status.failed_stage as keyof typeof STAGE_LABELS] ?? status.failed_stage} failed after retries.
          Resume Build to pick up.
        </p>
      )}

      {[
        "sprint_in_progress",
        "all_sprints_complete",
        "sprint_complete",
        "design_approved",
        "change_requested",
        "impact_analyzed",
        "replanning",
        "resuming_from_change",
      ].includes((status?.state || project?.status || "").toLowerCase()) && !isRunning && (
        <RequirementChangePanel
          projectId={project.project_id}
          onChangeApplied={onChangeApplied}
        />
      )}

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Project?</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Are you sure you want to delete "{project.name}"? This will erase the workspace, generated files, logs, and artifacts permanently.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" size="sm" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>
              {deleting && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}
              Delete Project
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

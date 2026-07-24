import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { Loader2, Plus, Sparkles } from "lucide-react"

import { api, type ProjectSummary } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Resizer } from "@/components/ui/resizer"
import { NewProjectDialog } from "@/components/NewProjectDialog"
import { ProjectWorkspace } from "@/pages/ProjectWorkspace"
import { useResizable } from "@/hooks/useResizable"
import { cn } from "@/lib/utils"

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  active: "warning",
  complete: "success",
  failed: "destructive",
}

export function Projects() {
  const { projectId } = useParams<{ projectId: string }>()
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const navigate = useNavigate()
  const rail = useResizable({ axis: "width", initial: 260, min: 200, max: 420, storageKey: "aidevos:project-rail-width" })

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]))
  }, [projectId])

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex h-full shrink-0 flex-col overflow-hidden border-r border-border" style={{ width: rail.size }}>
        <div className="flex items-center justify-between border-b border-border px-4 py-4">
          <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Projects</h2>
          <Button size="icon" variant="ghost" className="size-6" onClick={() => setDialogOpen(true)}>
            <Plus className="size-3.5" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {projects === null && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> Loading&hellip;
            </div>
          )}

          {projects?.length === 0 && (
            <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
              <Sparkles className="size-5 text-primary" />
              <p className="text-xs font-medium">No projects yet</p>
              <Button size="sm" className="mt-1" onClick={() => setDialogOpen(true)}>
                <Plus /> New Project
              </Button>
            </div>
          )}

          {projects?.map((project) => (
            <button
              key={project.project_id}
              onClick={() => navigate(`/projects/${project.project_id}`)}
              className={cn(
                "mb-1 flex w-full flex-col gap-1 rounded-md px-3 py-2 text-left transition-colors",
                projectId === project.project_id ? "bg-accent" : "hover:bg-accent/50",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{project.name}</span>
                <Badge variant={STATUS_VARIANT[project.status] ?? "muted"} className="shrink-0">
                  {project.status}
                </Badge>
              </div>
              <span className="truncate text-[11px] text-muted-foreground">{project.current_stage}</span>
            </button>
          ))}
        </div>
      </div>

      <Resizer direction="vertical" onPointerDown={rail.onPointerDown} />

      <div className="min-w-0 flex-1 overflow-hidden">
        {projectId ? (
          <ProjectWorkspace key={projectId} projectId={projectId} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Sparkles className="size-6" />
            </div>
            <p className="text-sm font-medium">Select a project, or start a new one</p>
            <p className="max-w-sm text-xs text-muted-foreground">
              Describe what you want built -- the AI team plans, designs, builds, and reviews it end to end.
            </p>
            <Button className="mt-2" onClick={() => setDialogOpen(true)}>
              <Plus /> New Project
            </Button>
          </div>
        )}
      </div>

      <NewProjectDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(newId) => navigate(`/projects/${newId}`)}
      />
    </div>
  )
}

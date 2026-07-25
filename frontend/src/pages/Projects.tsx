import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { Loader2, Plus, Sparkles, Trash2, FolderKanban } from "lucide-react"

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
  const rail = useResizable({ axis: "width", initial: 280, min: 220, max: 440, storageKey: "aidevos:project-rail-width" })

  function loadProjects() {
    api.listProjects().then(setProjects).catch(() => setProjects([]))
  }

  useEffect(() => {
    loadProjects()
  }, [projectId])

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (confirm("Are you sure you want to delete this project?")) {
      await api.deleteProject(id)
      loadProjects()
      if (projectId === id) {
        navigate("/projects")
      }
    }
  }

  return (
    <div className="flex h-full overflow-hidden bg-slate-950/80">
      {/* Left Rail Sidebar: Projects List */}
      <div className="flex h-full shrink-0 flex-col overflow-hidden border-r border-white/10 bg-slate-950/60 backdrop-blur-2xl" style={{ width: rail.size }}>
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-4">
          <h2 className="text-xs font-bold tracking-wider text-slate-300 uppercase flex items-center gap-2">
            <FolderKanban className="size-4 text-indigo-400" /> Studio Projects
          </h2>
          <Button size="icon" variant="ghost" className="size-7 text-slate-400 hover:text-white hover:bg-white/5" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-2.5">
          {projects === null && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-slate-400">
              <Loader2 className="size-4 animate-spin text-indigo-400" /> Loading projects…
            </div>
          )}

          {projects?.length === 0 && (
            <div className="flex flex-col items-center gap-3 px-3 py-12 text-center">
              <div className="flex size-10 items-center justify-center rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
                <Sparkles className="size-5" />
              </div>
              <p className="text-xs font-medium text-slate-300">No projects created</p>
              <Button size="sm" className="mt-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={() => setDialogOpen(true)}>
                <Plus className="mr-1 size-3" /> New Project
              </Button>
            </div>
          )}

          {projects?.map((project) => (
            <div
              key={project.project_id}
              onClick={() => navigate(`/projects/${project.project_id}`)}
              className={cn(
                "group relative mb-2 flex w-full flex-col gap-1.5 rounded-xl px-3.5 py-3 text-left transition-all cursor-pointer border",
                projectId === project.project_id
                  ? "bg-indigo-600/20 border-indigo-500/50 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                  : "bg-slate-900/30 border-white/5 hover:bg-slate-900/60 hover:border-white/10",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-bold text-white">{project.name}</span>
                <div className="flex items-center gap-1.5">
                  <Badge variant={STATUS_VARIANT[project.status] ?? "muted"} className="shrink-0 text-[10px]">
                    {project.status}
                  </Badge>
                  <button
                    onClick={(e) => handleDelete(e, project.project_id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-400 hover:text-rose-400 rounded hover:bg-white/5"
                    title="Delete Project"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
              <span className="truncate text-[11px] text-slate-400 font-mono">{project.current_stage}</span>
            </div>
          ))}
        </div>
      </div>

      <Resizer direction="vertical" onPointerDown={rail.onPointerDown} />

      {/* Main Workspace */}
      <div className="min-w-0 flex-1 overflow-hidden">
        {projectId ? (
          <ProjectWorkspace key={projectId} projectId={projectId} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center p-6 bg-slate-950/40">
            <div className="flex size-16 items-center justify-center rounded-2xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 shadow-[0_0_30px_rgba(99,102,241,0.25)]">
              <Sparkles className="size-8" />
            </div>
            <h3 className="text-lg font-bold text-white">Select a Workspace or Initialize AI Project</h3>
            <p className="max-w-md text-xs text-slate-400 leading-relaxed">
              Describe your software application -- the autonomous 12-stage AI dev team will architect, design, write code, run security checks, and generate complete documentation.
            </p>
            <Button className="mt-2 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold" onClick={() => setDialogOpen(true)}>
              <Plus className="mr-1.5 size-4" /> Create New Project
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

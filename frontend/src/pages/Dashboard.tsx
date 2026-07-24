import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { CheckCircle2, Loader2, Plus, Sparkles, XCircle, PauseCircle } from "lucide-react"

import { api, type ProjectSummary } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { NewProjectDialog } from "@/components/NewProjectDialog"

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  active: "warning",
  complete: "success",
  failed: "destructive",
}

export function Dashboard() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]))
  }, [])

  const total = projects?.length ?? 0
  const active = projects?.filter((p) => p.status === "active").length ?? 0
  const complete = projects?.filter((p) => p.status === "complete").length ?? 0
  const failed = projects?.filter((p) => p.status === "failed").length ?? 0
  const recent = [...(projects ?? [])]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 6)

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Overview of everything the AI team is working on.</p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus />
          New Project
        </Button>
      </header>

      {projects === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading&hellip;
        </div>
      ) : (
        <>
          <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard icon={<Sparkles className="size-4" />} label="Total Projects" value={total} />
            <StatCard icon={<Loader2 className="size-4" />} label="In Progress" value={active} accent="text-warning" />
            <StatCard icon={<CheckCircle2 className="size-4" />} label="Complete" value={complete} accent="text-success" />
            <StatCard icon={<XCircle className="size-4" />} label="Failed" value={failed} accent="text-destructive" />
          </div>

          <h2 className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Recent Projects</h2>

          {recent.length === 0 && (
            <div className="mt-8 flex flex-col items-center gap-3 text-center">
              <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Sparkles className="size-6" />
              </div>
              <p className="text-sm font-medium">No projects yet</p>
              <p className="max-w-sm text-xs text-muted-foreground">
                Create your first project and describe the app you want -- the AI team plans, designs, builds, and
                reviews it end to end.
              </p>
              <Button className="mt-2" onClick={() => setDialogOpen(true)}>
                <Plus /> New Project
              </Button>
            </div>
          )}

          {recent.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {recent.map((project) => (
                <Card
                  key={project.project_id}
                  className="cursor-pointer transition-colors hover:border-primary/50"
                  onClick={() => navigate(`/projects/${project.project_id}`)}
                >
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-base">{project.name}</CardTitle>
                      <Badge variant={STATUS_VARIANT[project.status] ?? "muted"}>{project.status}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <PauseCircle className="size-3" /> {project.current_stage}
                    </span>
                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {projects.length > recent.length && (
            <button
              onClick={() => navigate("/projects")}
              className="mt-4 text-xs font-medium text-primary hover:underline"
            >
              View all {projects.length} projects &rarr;
            </button>
          )}
        </>
      )}

      <NewProjectDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(projectId) => navigate(`/projects/${projectId}`)}
      />
    </div>
  )
}

function StatCard({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: number; accent?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-4">
        <div className={`flex size-9 items-center justify-center rounded-lg bg-accent/50 ${accent ?? "text-muted-foreground"}`}>
          {icon}
        </div>
        <div>
          <p className="text-lg font-semibold leading-none">{value}</p>
          <p className="text-[11px] text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

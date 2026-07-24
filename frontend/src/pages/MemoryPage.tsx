import { useEffect, useState } from "react"
import { Layers } from "lucide-react"

import { api, type MemorySummary, type ProjectSummary } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function MemoryPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [memory, setMemory] = useState<MemorySummary | null>(null)

  useEffect(() => {
    api.listProjects().then((list) => {
      setProjects(list)
      if (list.length > 0) setSelected(list[0].project_id)
    })
  }, [])

  useEffect(() => {
    if (!selected) return
    api.getMemory(selected).then(setMemory).catch(() => setMemory(null))
  }, [selected])

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Memory</h1>
        <p className="text-sm text-muted-foreground">What the system remembers for a project -- debug/inspector view.</p>
      </header>

      <div className="mb-5 flex flex-wrap gap-2">
        {projects.map((project) => (
          <button
            key={project.project_id}
            onClick={() => setSelected(project.project_id)}
            className={`rounded-full border px-3 py-1 text-xs ${
              selected === project.project_id ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
            }`}
          >
            {project.name}
          </button>
        ))}
      </div>

      {memory && (
        <>
          <div className="mb-6 grid grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-muted-foreground">Lessons</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{memory.lesson_count}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-muted-foreground">Trajectories</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{memory.trajectory_count}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-muted-foreground">Knowledge Entries</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{memory.knowledge_entry_count}</CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Stored Records</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {memory.records.length === 0 && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Layers className="size-3.5" /> No records stored for this project yet.
                </p>
              )}
              {memory.records.map((record) => (
                <div key={record.key} className="rounded-lg border border-border p-3">
                  <p className="font-mono text-xs font-medium">{record.key}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{record.value_preview}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

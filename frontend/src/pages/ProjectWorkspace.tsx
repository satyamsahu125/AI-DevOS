import { useCallback, useEffect, useState } from "react"
import { Loader2 } from "lucide-react"

import { api, type ProjectDetail } from "@/lib/api"
import { useWorkflowStatus } from "@/hooks/useWorkflowStatus"
import { useProjectLogs } from "@/hooks/useProjectLogs"
import { useProjectFiles } from "@/hooks/useProjectFiles"
import { useResizable } from "@/hooks/useResizable"
import { Resizer } from "@/components/ui/resizer"
import { WorkflowPanel } from "@/components/workspace/WorkflowPanel"
import { ChatPanel } from "@/components/workspace/ChatPanel"
import { ProjectPanel } from "@/components/workspace/ProjectPanel"
import { FileExplorer } from "@/components/workspace/FileExplorer"
import { BottomPanel } from "@/components/workspace/BottomPanel"

interface ProjectWorkspaceProps {
  projectId: string
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

  const leftColumnWidth = useResizable({ axis: "width", initial: 340, min: 260, max: 560, storageKey: "aidevos:left-column-width" })
  const liveOutputHeight = useResizable({ axis: "height", initial: 260, min: 120, max: 560, storageKey: "aidevos:live-output-height" })

  const { status } = useWorkflowStatus(projectId ?? null)
  const logs = useProjectLogs(projectId ?? null)
  const files = useProjectFiles(projectId ?? null)

  const refreshProject = useCallback(() => {
    if (!projectId) return
    api.getProject(projectId).then(setProject).catch(() => setProject(null))
  }, [projectId])

  useEffect(() => {
    refreshProject()
  }, [refreshProject])

  // Re-fetch the project record (stages_completed / artifacts list) whenever
  // the workflow status or file tree changes, so the Artifacts tab and
  // sidebar stay current without a manual refresh.
  useEffect(() => {
    refreshProject()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.completed_stages.length, files.backend.length, files.frontend.length])

  async function handleStartBuild(requestText: string) {
    if (!projectId) return
    setStarting(true)
    try {
      // This blocks until all 12 stages finish -- we intentionally don't
      // await UI state on it; the logs/status polling above already reflects
      // progress well before this promise resolves.
      api.startWorkflow(projectId, requestText).finally(() => setStarting(false))
    } catch {
      setStarting(false)
    }
  }

  async function handleRetryStage(stage: string) {
    if (!projectId || !project) return
    await api.runStage(projectId, stage, project.description)
  }

  async function handleStopBuild() {
    if (!projectId) return
    setStopping(true)
    try {
      await api.stopWorkflow(projectId)
    } finally {
      setStopping(false)
    }
  }

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" /> Loading project…
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <WorkflowPanel status={status} />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex h-full shrink-0 flex-col overflow-hidden border-r border-border" style={{ width: leftColumnWidth.size }}>
          <div className="shrink-0 overflow-hidden" style={{ height: liveOutputHeight.size }}>
            <BottomPanel projectId={projectId} logs={logs} artifacts={project.artifacts} />
          </div>
          <Resizer direction="horizontal" onPointerDown={liveOutputHeight.onPointerDown} />

          <ProjectPanel
            project={project}
            status={status}
            onStartBuild={handleStartBuild}
            onStopBuild={handleStopBuild}
            starting={starting}
            stopping={stopping}
          />

          <div className="min-h-0 flex-1 overflow-hidden">
            <FileExplorer projectId={projectId} files={files} />
          </div>
        </div>

        <Resizer direction="vertical" onPointerDown={leftColumnWidth.onPointerDown} />

        <div className="min-w-0 flex-1 overflow-hidden">
          <ChatPanel logs={logs} onRetryStage={handleRetryStage} />
        </div>
      </div>
    </div>
  )
}

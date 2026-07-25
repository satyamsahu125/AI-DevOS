import { useCallback, useEffect, useState } from "react"
import { Loader2, Code2, FileText, Terminal, BarChart3, Sparkles } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { api, type ProjectDetail } from "@/lib/api"
import { useWorkflowStatus } from "@/hooks/useWorkflowStatus"
import { useProjectLogs } from "@/hooks/useProjectLogs"
import { useProjectFiles } from "@/hooks/useProjectFiles"
import { useResizable } from "@/hooks/useResizable"
import { Resizer } from "@/components/ui/resizer"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"

import { WorkflowPanel } from "@/components/workspace/WorkflowPanel"
import { ChatPanel } from "@/components/workspace/ChatPanel"
import { ProjectPanel } from "@/components/workspace/ProjectPanel"
import { FileExplorer } from "@/components/workspace/FileExplorer"
import { BottomPanel } from "@/components/workspace/BottomPanel"
import { DesignReviewModal } from "@/components/workspace/DesignReviewModal"

interface ProjectWorkspaceProps {
  projectId: string
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [designReviewOpen, setDesignReviewOpen] = useState(false)
  const [activeWorkbenchTab, setActiveWorkbenchTab] = useState("files")

  const navigate = useNavigate()

  const rightColumnWidth = useResizable({ axis: "width", initial: 480, min: 360, max: 720, storageKey: "aidevos:right-column-width" })

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

  useEffect(() => {
    refreshProject()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.completed_stages.length, files.backend.length, files.frontend.length])

  // Automatically open Human Action popup modal if the backend is waiting on user action
  useEffect(() => {
    const st = status?.state ? String(status.state).toLowerCase() : ""
    if (
      status?.requires_user_action ||
      st === "design_review_pending" ||
      st.includes("design_review") ||
      st === "design_ready" ||
      st === "awaiting_human" ||
      st === "human_action_required"
    ) {
      setDesignReviewOpen(true)
    }
  }, [status?.requires_user_action, status?.state])

  async function handleStartBuild(requestText: string) {
    if (!projectId) return
    setStarting(true)
    try {
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

  function handleProjectDeleted() {
    navigate("/projects")
  }

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        <Loader2 className="mr-2 size-4 animate-spin text-indigo-500" /> Loading AI Studio workspace…
      </div>
    )
  }

  const isHumanActionRequired = Boolean(
    status?.requires_user_action ||
    status?.state?.toLowerCase().includes("design_review") ||
    status?.state?.toLowerCase() === "design_ready" ||
    status?.state?.toLowerCase() === "awaiting_human" ||
    status?.state?.toLowerCase() === "human_action_required"
  )

  return (
    <div className="flex h-full flex-col overflow-hidden bg-slate-950/60 backdrop-blur-3xl">
      {/* Top Pipeline Bar */}
      <WorkflowPanel
        status={status}
        onOpenDesignReview={() => setDesignReviewOpen(true)}
      />

      {/* Human Action Required Alert Banner */}
      {isHumanActionRequired && (
        <div className="flex items-center justify-between border-b border-amber-500/30 bg-amber-500/10 px-6 py-2.5 backdrop-blur-md">
          <div className="flex items-center gap-2 text-xs font-medium text-amber-300">
            <Sparkles className="size-4 animate-pulse text-amber-400" />
            <span>Human Action Required: System design specification is ready for your review and approval.</span>
          </div>
          <Button
            size="sm"
            onClick={() => setDesignReviewOpen(true)}
            className="h-7 rounded-lg bg-amber-500 px-3.5 text-xs font-semibold text-zinc-950 shadow-lg shadow-amber-500/20 hover:bg-amber-400"
          >
            Review & Approve Design
          </Button>
        </div>
      )}

      {/* Main Studio Workspace Split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Center: Conversational AI Prompt Workspace (Claude / AI Studio Style) */}
        <div className="min-w-0 flex-1 overflow-hidden">
          <ChatPanel logs={logs} onRetryStage={handleRetryStage} onSendMessage={handleStartBuild} />
        </div>

        <Resizer direction="vertical" onPointerDown={rightColumnWidth.onPointerDown} />

        {/* Right: Studio Workbench (Files, Artifact Specs, Console Logs, Metrics) */}
        <div className="flex h-full shrink-0 flex-col overflow-hidden border-l border-white/10 bg-slate-900/40 backdrop-blur-xl" style={{ width: rightColumnWidth.size }}>
          <Tabs value={activeWorkbenchTab} onValueChange={setActiveWorkbenchTab} className="flex h-full flex-col gap-0">
            {/* Workbench Tab Bar */}
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-2 bg-slate-950/60">
              <TabsList className="h-9 bg-slate-900/80 p-1 border border-white/5">
                <TabsTrigger value="files" className="text-xs px-3 py-1 data-[state=active]:bg-indigo-600/30 data-[state=active]:text-indigo-300">
                  <Code2 className="size-3.5 mr-1.5 text-indigo-400" /> Files & Code
                </TabsTrigger>
                <TabsTrigger value="console" className="text-xs px-3 py-1 data-[state=active]:bg-indigo-600/30 data-[state=active]:text-indigo-300">
                  <Terminal className="size-3.5 mr-1.5 text-emerald-400" /> Live Logs
                </TabsTrigger>
                <TabsTrigger value="artifacts" className="text-xs px-3 py-1 data-[state=active]:bg-indigo-600/30 data-[state=active]:text-indigo-300">
                  <FileText className="size-3.5 mr-1.5 text-amber-400" /> System Specs
                </TabsTrigger>
                <TabsTrigger value="settings" className="text-xs px-3 py-1 data-[state=active]:bg-indigo-600/30 data-[state=active]:text-indigo-300">
                  <BarChart3 className="size-3.5 mr-1.5 text-cyan-400" /> Metrics
                </TabsTrigger>
              </TabsList>
            </div>

            {/* Files & Code Tab */}
            <TabsContent value="files" className="flex-1 overflow-hidden m-0">
              <FileExplorer projectId={projectId} files={files} />
            </TabsContent>

            {/* Live Output Console Tab */}
            <TabsContent value="console" className="flex-1 overflow-hidden m-0">
              <BottomPanel projectId={projectId} logs={logs} artifacts={project.artifacts} />
            </TabsContent>

            {/* Artifact Specs Tab */}
            <TabsContent value="artifacts" className="flex-1 overflow-hidden m-0">
              <BottomPanel projectId={projectId} logs={logs} artifacts={project.artifacts} />
            </TabsContent>

            {/* Metrics & Controls Tab */}
            <TabsContent value="settings" className="flex-1 overflow-y-auto m-0 p-2">
              <ProjectPanel
                project={project}
                status={status}
                onStartBuild={handleStartBuild}
                onStopBuild={handleStopBuild}
                onDeleteProject={handleProjectDeleted}
                onOpenDesignReview={() => setDesignReviewOpen(true)}
                starting={starting}
                stopping={stopping}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Design Approval Modal Gate */}
      <DesignReviewModal
        projectId={projectId}
        open={designReviewOpen}
        onOpenChange={setDesignReviewOpen}
        onActionCompleted={refreshProject}
      />
    </div>
  )
}

import { useCallback, useEffect, useState } from "react"
import { Loader2, Code2, FileText, Terminal, BarChart3, Sparkles } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { api, type ProjectDetail, type LogEvent, type WorkflowStatus } from "@/lib/api"
import { useWorkflowStatus } from "@/hooks/useWorkflowStatus"
import { useProjectLogs } from "@/hooks/useProjectLogs"
import { useProjectFiles } from "@/hooks/useProjectFiles"
import { useProjectWebSocket, type WSMessage } from "@/hooks/useProjectWebSocket"
import { useResizable } from "@/hooks/useResizable"
import { Resizer } from "@/components/ui/resizer"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"

import { QAPanel } from "@/components/qa/QAPanel"
import { WorkflowPanel } from "@/components/workspace/WorkflowPanel"
import { ChatPanel } from "@/components/workspace/ChatPanel"
import { ProjectPanel } from "@/components/workspace/ProjectPanel"
import { FileExplorer } from "@/components/files/FileExplorer"
import { ArtifactViewer } from "@/components/artifacts/ArtifactViewer"
import { ApprovalPanel } from "@/components/approval/ApprovalPanel"
import { BottomPanel } from "@/components/workspace/BottomPanel"
import { DesignReviewModal } from "@/components/workspace/DesignReviewModal"
import { LiveLogsPanel } from "@/components/workspace/LiveLogsPanel"
import { MetricsPanel } from "@/components/metrics/MetricsPanel"

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

  const { status: initialStatus } = useWorkflowStatus(projectId ?? null)
  const initialLogs = useProjectLogs(projectId ?? null)
  const initialFiles = useProjectFiles(projectId ?? null)

  // State declarations must come before any callbacks that reference their setters.
  const [pipelineState, setPipelineState] = useState({
    state: "empty",
    current_stage: null as string | null,
    stages_completed: [] as string[],
  })
  const [liveLogs, setLiveLogs] = useState<string[]>([])
  const [logEvents, setLogEvents] = useState<LogEvent[]>([])
  const [liveFiles, setLiveFiles] = useState<{ backend: string[]; frontend: string[] }>({
    backend: [],
    frontend: [],
  })

  // FIX-D: refreshStatus fetches GET /workflow/{id} and syncs pipelineState.
  // This is the single source of truth for UI state transitions — used after
  // user actions (qa/complete, design-review approval) and as a polling fallback
  // when WebSocket is offline.
  const refreshStatus = useCallback(async () => {
    if (!projectId) return
    try {
      const next = await api.getWorkflowStatus(projectId)
      if (next) {
        setPipelineState({
          state: next.state || "empty",
          current_stage: next.current_stage || null,
          stages_completed: next.completed_stages || [],
        })
      }
    } catch {
      // ignore transient network errors
    }
  }, [projectId])

  // Sync initial state once fetched
  useEffect(() => {
    if (initialStatus) {
      setPipelineState({
        state: initialStatus.state || "empty",
        current_stage: initialStatus.current_stage || null,
        stages_completed: initialStatus.completed_stages || [],
      })
    }
  }, [initialStatus])

  useEffect(() => {
    if (initialLogs.length > 0 && logEvents.length === 0) {
      setLogEvents(initialLogs)
      setLiveLogs(initialLogs.map((l) => `[${l.stage}] ${l.message}`))
    }
  }, [initialLogs, logEvents.length])

  useEffect(() => {
    if (initialFiles.backend.length > 0 || initialFiles.frontend.length > 0) {
      setLiveFiles(initialFiles)
    }
  }, [initialFiles])

  // FIX-D: Poll GET /workflow/{id} every 5 s when the pipeline is active.
  // This is a safety-net fallback for when the WebSocket is offline or has not yet
  // delivered a status_update (e.g. right after qa/complete fires the background task).
  // The poll stops automatically once the pipeline reaches a terminal state.
  useEffect(() => {
    const TERMINAL_STATES = new Set(["done", "deployable", "failed", "empty"])
    if (TERMINAL_STATES.has(pipelineState.state)) return
    const id = setInterval(refreshStatus, 5000)
    return () => clearInterval(id)
  }, [pipelineState.state, refreshStatus])

  const handleWSMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case "status_update":
        setPipelineState({
          state: (msg.state as string) || "empty",
          current_stage: (msg.current_stage as string) || null,
          stages_completed: (msg.stages_completed as string[]) || [],
        })
        break

      case "stage_started":
        setLiveLogs((prev) => [...prev, `▶ ${msg.stage} started (attempt ${msg.attempt || 1})`])
        setPipelineState((prev) => ({
          ...prev,
          current_stage: (msg.stage as string) || null,
        }))
        break

      case "stage_complete":
        setLiveLogs((prev) => [
          ...prev,
          `✓ ${msg.stage} approved on attempt ${msg.attempt || 1} (${msg.duration_seconds || 0}s)`,
        ])
        setPipelineState((prev) => ({
          ...prev,
          stages_completed: [...new Set([...prev.stages_completed, msg.stage as string])],
        }))
        break

      case "stage_retry":
        setLiveLogs((prev) => [
          ...prev,
          `↩ ${msg.stage} retrying (attempt ${msg.attempt}): ${String(msg.feedback || "").slice(0, 80)}`,
        ])
        break

      case "stage_failed":
        setLiveLogs((prev) => [...prev, `✗ ${msg.stage} failed: ${msg.reason}`])
        break

      case "log_line":
        setLiveLogs((prev) => [...prev, msg.line || ""])
        break

      case "file_added": {
        const filePath = String(msg.file_path || "")
        setLiveLogs((prev) => [...prev, `📄 Generated: ${filePath}`])
        setLiveFiles((prev) => {
          if (filePath.startsWith("backend/")) {
            const rel = filePath.replace("backend/", "")
            if (!prev.backend.includes(rel)) return { ...prev, backend: [...prev.backend, rel] }
          } else if (filePath.startsWith("frontend/")) {
            const rel = filePath.replace("frontend/", "")
            if (!prev.frontend.includes(rel)) return { ...prev, frontend: [...prev.frontend, rel] }
          }
          return prev
        })
        break
      }

      case "qa_question":
        setLiveLogs((prev) => [...prev, `❓ Q&A: ${msg.question}`])
        break

      case "approval_needed":
        setLiveLogs((prev) => [...prev, `⏸ Waiting for approval: ${msg.stage}`])
        break

      case "change_analyzed":
        setLiveLogs((prev) => [
          ...prev,
          `🔍 Impact: ${(msg.affected_stages as string[])?.length || 0} stages affected`,
        ])
        break

      case "pipeline_done":
        setLiveLogs((prev) => [...prev, `🎉 Pipeline complete! ${msg.total_stages || 0} stages done`])
        setPipelineState((prev) => ({
          ...prev,
          state: "done",
          stages_completed: (msg.stages_completed as string[]) || prev.stages_completed,
        }))
        break
    }

    if (msg.message || msg.line) {
      setLogEvents((prev) => [
        ...prev,
        {
          id: Date.now() + Math.floor(Math.random() * 1000),
          stage: String(msg.stage || "Pipeline"),
          level: msg.type.includes("failed") ? "error" : msg.type.includes("retry") ? "warning" : "info",
          message: String(msg.message || msg.line || ""),
          created_at: String(msg.timestamp || new Date().toISOString()),
        },
      ])
    }
  }, [])

  const { connected } = useProjectWebSocket(projectId, handleWSMessage)

  const refreshProject = useCallback(() => {
    if (!projectId) return
    api.getProject(projectId).then(setProject).catch(() => setProject(null))
  }, [projectId])

  useEffect(() => {
    refreshProject()
  }, [refreshProject])

  // Automatically open Human Action popup modal if backend requires user action
  useEffect(() => {
    const st = pipelineState.state.toLowerCase()
    if (
      st === "design_review_pending" ||
      st.includes("design_review") ||
      st === "design_ready" ||
      st === "awaiting_human" ||
      st === "human_action_required"
    ) {
      setDesignReviewOpen(true)
    }
  }, [pipelineState.state])

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

  const effectiveStatus: WorkflowStatus = {
    project_id: projectId,
    state: pipelineState.state,
    current_stage: pipelineState.current_stage,
    completed_stages: pipelineState.stages_completed,
    failed_stage: initialStatus?.failed_stage || null,
    total_stages: 14,
    progress_percent: Math.round((100 * pipelineState.stages_completed.length) / 14),
    status:
      pipelineState.state === "done" || pipelineState.state === "deployable"
        ? "complete"
        : pipelineState.state === "failed"
        ? "failed"
        : pipelineState.current_stage
        ? "running"
        : "not_started",
    requires_user_action: ["design_review_pending", "qa_pending"].includes(pipelineState.state),
  }

  const isHumanActionRequired = Boolean(
    effectiveStatus.requires_user_action ||
    pipelineState.state.toLowerCase().includes("design_review") ||
    pipelineState.state.toLowerCase() === "design_ready" ||
    pipelineState.state.toLowerCase() === "awaiting_human" ||
    pipelineState.state.toLowerCase() === "human_action_required"
  )

  const isAwaitingHumanApproval = Boolean(
    pipelineState.state.toLowerCase() === "awaiting_human_approval" ||
    pipelineState.state.toLowerCase() === "awaiting_human"
  )

  return (
    <div className="flex h-full flex-col overflow-hidden bg-slate-950/60 backdrop-blur-3xl">
      {/* Top Pipeline Bar */}
      <div className="relative flex items-center justify-between border-b border-white/10 bg-slate-950/80 px-4 py-2">
        <WorkflowPanel
          status={effectiveStatus}
          onOpenDesignReview={() => setDesignReviewOpen(true)}
        />
        {/* WebSocket Connection Status Indicator */}
        <div className="absolute right-4 top-3 flex items-center gap-2 text-[11px] text-white/40">
          <div
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              connected ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
            }`}
            title={connected ? "WebSocket Connected" : "WebSocket Disconnected"}
          />
          <span className="hidden sm:inline font-mono">{connected ? "Live" : "Offline"}</span>
        </div>
      </div>

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
        {/* Center: Conversational AI Prompt Workspace / Interactive Q&A / Approval Panel */}
        <div className="min-w-0 flex-1 overflow-hidden flex flex-col">
          {pipelineState.state === "qa_pending" || pipelineState.state === "qa_in_progress" ? (
            // FIX-D: onComplete must refresh pipelineState (not just project metadata)
            // so the center panel stops rendering QAPanel after qa/complete fires.
            <QAPanel projectId={projectId} onComplete={async () => { refreshProject(); await refreshStatus() }} />
          ) : isAwaitingHumanApproval ? (
            <ApprovalPanel
              projectId={projectId}
              stage={pipelineState.current_stage || "architect"}
              onDecision={() => refreshProject()}
            />
          ) : (
            <ChatPanel logs={logEvents} projectId={projectId} onRetryStage={handleRetryStage} onSendMessage={handleStartBuild} />
          )}
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
              <FileExplorer projectId={projectId} files={liveFiles} />
            </TabsContent>

            {/* Live Output Console Tab */}
            <TabsContent value="console" className="flex-1 overflow-hidden m-0">
              {liveLogs.length > 0 ? (
                <LiveLogsPanel logs={liveLogs} />
              ) : (
                <BottomPanel projectId={projectId} logs={logEvents} artifacts={project.artifacts} />
              )}
            </TabsContent>

            {/* Artifact Specs Tab */}
            <TabsContent value="artifacts" className="flex-1 overflow-hidden m-0">
              <ArtifactViewer
                projectId={projectId}
                stagesCompleted={pipelineState.stages_completed}
              />
            </TabsContent>

            {/* Metrics & Controls Tab */}
            <TabsContent value="settings" className="flex-1 overflow-y-auto m-0 p-2 space-y-4">
              <MetricsPanel projectId={projectId} />
              <ProjectPanel
                project={project}
                status={effectiveStatus}
                onStartBuild={handleStartBuild}
                onStopBuild={handleStopBuild}
                onDeleteProject={handleProjectDeleted}
                onOpenDesignReview={() => setDesignReviewOpen(true)}
                onChangeApplied={refreshProject}
                starting={starting}
                stopping={stopping}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Design Approval Modal Gate */}
      {/* FIX-D: onActionCompleted must refresh pipelineState so the design-review
          banner disappears and the pipeline advances in the UI */}
      <DesignReviewModal
        projectId={projectId}
        open={designReviewOpen}
        onOpenChange={setDesignReviewOpen}
        onActionCompleted={async () => { setDesignReviewOpen(false); refreshProject(); await refreshStatus() }}
      />
    </div>
  )
}

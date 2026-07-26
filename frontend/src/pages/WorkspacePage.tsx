import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { api, type ProjectDetail } from "../lib/api"
import { usePipeline } from "../hooks/usePipeline"
import { useLogs } from "../hooks/useLogs"
import { StageRail } from "../components/pipeline/StageRail"
import { QAPanel } from "../components/qa/QAPanel"
import { DesignReviewModal } from "../components/design/DesignReviewModal"
import { ChatPanel } from "../components/chat/ChatPanel"
import { LogsPanel } from "../components/logview/LogsPanel"
import { FileExplorer } from "../components/files/FileExplorer"
import { ArtifactsPanel } from "../components/artifacts/ArtifactsPanel"
import { MetricsPanel } from "../components/metrics/MetricsPanel"
import { Spinner } from "../components/ui/Spinner"

type Tab = "files" | "logs" | "artifacts" | "metrics"

// ── Workspace layout ──────────────────────────────────────────────────────

export function WorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [tab, setTab] = useState<Tab>("logs")
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [designOpen, setDesignOpen] = useState(false)

  const { pipeline, liveLogs, connected, refresh } = usePipeline(projectId ?? null)
  const logEvents = useLogs(projectId ?? null)

  const loadProject = useCallback(() => {
    if (!projectId) return
    api.getProject(projectId).then(setProject).catch(() => {})
  }, [projectId])

  useEffect(() => { loadProject() }, [loadProject])

  // Auto-open design review when backend requires it
  useEffect(() => {
    const s = pipeline.state.toLowerCase()
    if (s.includes("design_review") || s === "design_ready") setDesignOpen(true)
  }, [pipeline.state])

  async function handleStart() {
    if (!projectId || !project) return
    setStarting(true)
    try {
      await api.startWorkflow(projectId, project.description || `Build ${project.name}`)
      await refresh()
    } finally {
      setStarting(false)
    }
  }

  async function handleStop() {
    if (!projectId) return
    setStopping(true)
    try { await api.stopWorkflow(projectId) }
    finally { setStopping(false) }
  }

  async function handleContinue() {
    if (!projectId) return
    try { await api.continueWorkflow(projectId); await refresh() }
    catch { /* ignore */ }
  }

  // Determine center panel
  const s = pipeline.state.toLowerCase()
  const showQA = s === "qa_pending" || s === "qa_in_progress"
  const showEmpty = s === "empty" || !project

  // Status chip
  const chipColor =
    pipeline.status === "running"   ? "bg-indigo-500/15 text-indigo-300 border-indigo-500/20" :
    pipeline.status === "complete"  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/20" :
    pipeline.status === "failed"    ? "bg-rose-500/15 text-rose-300 border-rose-500/20" :
    pipeline.status === "paused"    ? "bg-amber-500/15 text-amber-300 border-amber-500/20" :
                                      "bg-zinc-800 text-zinc-500 border-zinc-700"

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center bg-zinc-950">
        <Spinner size={28} className="text-indigo-500" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-zinc-950 text-zinc-100">

      {/* ── Top bar ───────────────────────────────────────────────────── */}
      <header className="flex shrink-0 flex-col border-b border-zinc-800/60 bg-zinc-950">
        {/* Row 1: nav + controls */}
        <div className="flex items-center justify-between gap-4 px-5 py-2.5">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => navigate("/projects")}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-indigo-600">
              <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h1 className="truncate text-sm font-semibold text-zinc-100">{project.name}</h1>
            <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[10px] font-medium ${chipColor}`}>
              {pipeline.status === "running" && pipeline.current_stage
                ? pipeline.current_stage.replace(/_/g, " ")
                : pipeline.status === "not_started" ? "Not started"
                : pipeline.status}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {/* WS indicator */}
            <div className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] ${
              connected ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                        : "border-zinc-700 bg-zinc-800/60 text-zinc-600"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"}`} />
              {connected ? "Live" : "Polling"}
            </div>

            {pipeline.status === "running" ? (
              <button
                onClick={handleStop} disabled={stopping}
                className="flex items-center gap-1.5 rounded-lg bg-rose-600/20 border border-rose-500/20 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-600/30 disabled:opacity-40"
              >
                {stopping && <Spinner size={12} />}■ Stop
              </button>
            ) : pipeline.status === "paused" || pipeline.state.toLowerCase() === "design_approved" ? (
              <button
                onClick={handleContinue}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
              >▶ Continue</button>
            ) : pipeline.status === "not_started" || pipeline.status === "stopped" ? (
              <button
                onClick={handleStart} disabled={starting}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
              >
                {starting && <Spinner size={12} />}▶ Start Build
              </button>
            ) : null}

            {pipeline.requires_user_action && (
              <button
                onClick={() => setDesignOpen(true)}
                className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-500/20 animate-pulse"
              >
                ⚡ Review Design
              </button>
            )}

            <a
              href={api.downloadUrl(projectId!)}
              target="_blank" rel="noreferrer"
              className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            >⬇ Download</a>
          </div>
        </div>

        {/* Row 2: stage rail */}
        <div className="border-t border-zinc-800/40 px-5 py-2.5">
          <StageRail
            completedStages={pipeline.stages_completed}
            currentStage={pipeline.current_stage}
            failedStage={pipeline.failed_stage}
          />
        </div>

        {/* Sprint progress bar if active */}
        {pipeline.total_sprints > 0 && (
          <div className="border-t border-zinc-800/40 px-5 py-1.5">
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-zinc-500">{pipeline.sprint_progress}</span>
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all"
                  style={{ width: `${Math.round(100 * pipeline.current_sprint / Math.max(pipeline.total_sprints, 1))}%` }}
                />
              </div>
              <span className="text-[10px] text-zinc-500">{pipeline.sprint_name}</span>
            </div>
          </div>
        )}
      </header>

      {/* ── Main content ──────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* Left: context panel */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r border-zinc-800/60">
          {showQA ? (
            <QAPanel
              projectId={projectId!}
              onComplete={async () => { loadProject(); await refresh() }}
            />
          ) : showEmpty ? (
            <EmptyState onStart={handleStart} starting={starting} />
          ) : (
            <ChatPanel
              projectId={projectId!}
              logEvents={logEvents}
              liveLogs={liveLogs}
              pipelineState={pipeline}
              onRetryStage={async (stage) => {
                await api.runStage(projectId!, stage, project.description)
                await refresh()
              }}
              onSubmitChange={async (desc) => {
                const res = await api.submitChange(projectId!, desc)
                await refresh()
                return res
              }}
            />
          )}
        </div>

        {/* Right: workbench */}
        <div className="flex w-[420px] shrink-0 flex-col overflow-hidden">
          {/* Tab bar */}
          <div className="flex shrink-0 border-b border-zinc-800/60 bg-zinc-900/50 px-3 py-1.5">
            {(["logs", "files", "artifacts", "metrics"] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  tab === t ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {t === "logs" ? "📋 Logs" : t === "files" ? "📁 Files" : t === "artifacts" ? "📦 Artifacts" : "📊 Metrics"}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === "logs"      && <LogsPanel events={logEvents} liveLogs={liveLogs} />}
            {tab === "files"     && <FileExplorer projectId={projectId!} />}
            {tab === "artifacts" && <ArtifactsPanel projectId={projectId!} completedStages={pipeline.stages_completed} />}
            {tab === "metrics"   && <MetricsPanel projectId={projectId!} />}
          </div>
        </div>
      </div>

      {/* Design review modal gate */}
      {designOpen && (
        <DesignReviewModal
          projectId={projectId!}
          onClose={() => setDesignOpen(false)}
          onActionCompleted={async () => {
            setDesignOpen(false)
            loadProject()
            await refresh()
          }}
        />
      )}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────

function EmptyState({ onStart, starting }: { onStart: () => void; starting: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-12 text-center">
      <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-zinc-900 ring-1 ring-zinc-800">
        <svg className="h-10 w-10 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      <div>
        <p className="text-base font-semibold text-zinc-300">Ready to build</p>
        <p className="mt-1 max-w-xs text-sm text-zinc-600">
          Start the pipeline to begin the autonomous development process. AI agents will handle everything from planning to code generation.
        </p>
      </div>
      <button
        onClick={onStart}
        disabled={starting}
        className="flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-medium text-white shadow-lg shadow-indigo-600/20 hover:bg-indigo-500 disabled:opacity-40"
      >
        {starting ? <Spinner size={16} /> : (
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        )}
        Start Build Pipeline
      </button>
    </div>
  )
}

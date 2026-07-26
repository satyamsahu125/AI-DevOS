import { useCallback, useEffect, useRef, useState } from "react"
import { api, type WorkflowStatus } from "../lib/api"
import { type WSMessage, useWebSocket } from "./useWebSocket"

export interface PipelineState {
  state: string
  status: WorkflowStatus["status"]
  current_stage: string | null
  stages_completed: string[]
  failed_stage: string | null
  progress_percent: number
  requires_user_action: boolean
  current_sprint: number
  total_sprints: number
  sprint_name: string
  sprint_progress: string
  estimated_completion: string
}

const EMPTY: PipelineState = {
  state: "empty",
  status: "not_started",
  current_stage: null,
  stages_completed: [],
  failed_stage: null,
  progress_percent: 0,
  requires_user_action: false,
  current_sprint: 0,
  total_sprints: 0,
  sprint_name: "",
  sprint_progress: "",
  estimated_completion: "",
}

const TERMINAL = new Set(["done", "deployable", "failed", "empty"])

function fromStatus(s: WorkflowStatus): PipelineState {
  return {
    state: s.state ?? "empty",
    status: s.status,
    current_stage: s.current_stage,
    stages_completed: s.completed_stages ?? [],
    failed_stage: s.failed_stage,
    progress_percent: s.progress_percent ?? 0,
    requires_user_action: s.requires_user_action ?? false,
    current_sprint: s.current_sprint ?? 0,
    total_sprints: s.total_sprints ?? 0,
    sprint_name: s.sprint_name ?? "",
    sprint_progress: s.sprint_progress ?? "",
    estimated_completion: s.estimated_completion ?? "",
  }
}

export function usePipeline(projectId: string | null) {
  const [pipeline, setPipeline] = useState<PipelineState>(EMPTY)
  const [liveLogs, setLiveLogs] = useState<string[]>([])

  // Fetch current status from REST
  const refresh = useCallback(async () => {
    if (!projectId) return
    try {
      const s = await api.getWorkflowStatus(projectId)
      setPipeline(fromStatus(s))
    } catch { /* ignore */ }
  }, [projectId])

  // Initial fetch
  useEffect(() => {
    if (!projectId) return
    setPipeline(EMPTY)
    setLiveLogs([])
    refresh()
  }, [projectId, refresh])

  // Poll every 5 s while pipeline is active
  useEffect(() => {
    if (!projectId) return
    if (TERMINAL.has(pipeline.state)) return
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [projectId, pipeline.state, refresh])

  // WebSocket handler
  const handleWS = useCallback((msg: WSMessage) => {
    const log = (line: string) => setLiveLogs(p => [...p.slice(-499), line])

    switch (msg.type) {
      case "status_update":
        setPipeline(p => ({
          ...p,
          state:            (msg.state as string) ?? p.state,
          current_stage:    (msg.current_stage as string) ?? null,
          stages_completed: (msg.stages_completed as string[]) ?? p.stages_completed,
        }))
        break

      case "stage_started":
        setPipeline(p => ({ ...p, current_stage: (msg.stage as string) ?? null }))
        log(`▶  ${msg.stage} started (attempt ${msg.attempt ?? 1})`)
        break

      case "stage_complete":
        setPipeline(p => ({
          ...p,
          stages_completed: [...new Set([...p.stages_completed, msg.stage as string])],
        }))
        log(`✓  ${msg.stage} done (${msg.duration_seconds ?? 0}s, attempt ${msg.attempt ?? 1})`)
        break

      case "stage_retry":
        log(`↩  ${msg.stage} retry ${msg.attempt}: ${String(msg.feedback ?? "").slice(0, 100)}`)
        break

      case "stage_failed":
        setPipeline(p => ({ ...p, failed_stage: msg.stage as string, state: "failed", status: "failed" }))
        log(`✗  ${msg.stage} failed: ${msg.reason}`)
        break

      case "log_line":
        log(msg.line ?? "")
        break

      case "file_added":
        log(`📄 ${msg.file_path}`)
        break

      case "qa_question":
        log(`❓ Q&A: ${msg.question}`)
        break

      case "approval_needed":
        log(`⏸  Waiting for approval: ${msg.stage}`)
        setPipeline(p => ({ ...p, requires_user_action: true }))
        break

      case "pipeline_done":
        setPipeline(p => ({
          ...p,
          state:            "done",
          status:           "complete",
          stages_completed: (msg.stages_completed as string[]) ?? p.stages_completed,
          progress_percent: 100,
        }))
        log(`🎉 Pipeline complete!`)
        break
    }
  }, [])

  const { connected } = useWebSocket(projectId, handleWS)

  return { pipeline, liveLogs, connected, refresh }
}

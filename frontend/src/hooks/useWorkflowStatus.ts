import { useEffect, useRef, useState } from "react"

import { api, type WorkflowStatus } from "@/lib/api"

/** Polls GET /workflow/{projectId} every few seconds while the pipeline is running. */
export function useWorkflowStatus(projectId: string | null, intervalMs = 3000) {
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false

    async function poll() {
      try {
        const next = await api.getWorkflowStatus(projectId!)
        if (!cancelled) {
          setStatus(next)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load workflow status")
      }
    }

    poll()
    timer.current = setInterval(poll, intervalMs)
    return () => {
      cancelled = true
      if (timer.current) clearInterval(timer.current)
    }
  }, [projectId, intervalMs])

  return { status, error }
}

import { useEffect, useState } from "react"

import { api, type WorkflowStatus } from "@/lib/api"

/** Fetches GET /workflow/{projectId} initial status without periodic polling. */
export function useWorkflowStatus(projectId: string | null) {
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false

    async function fetchStatus() {
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

    fetchStatus()
    return () => {
      cancelled = true
    }
  }, [projectId])

  return { status, error }
}

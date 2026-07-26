import { useEffect, useRef, useState } from "react"

import { api, type LogEvent } from "@/lib/api"

/** Fetches initial GET /projects/{projectId}/logs without periodic polling. */
export function useProjectLogs(projectId: string | null) {
  const [events, setEvents] = useState<LogEvent[]>([])
  const sinceId = useRef(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    sinceId.current = 0
    setEvents([])

    async function fetchLogs() {
      try {
        const next = await api.getLogs(projectId!, sinceId.current)
        if (next.length && !cancelled) {
          sinceId.current = next[next.length - 1].id
          setEvents(next)
        }
      } catch {
        // ignore network error
      }
    }

    fetchLogs()
    return () => {
      cancelled = true
    }
  }, [projectId])

  return events
}

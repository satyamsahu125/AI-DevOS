import { useEffect, useRef, useState } from "react"

import { api, type LogEvent } from "@/lib/api"

/** Polls GET /projects/{projectId}/logs, tailing from the last-seen event id (since_id). */
export function useProjectLogs(projectId: string | null, intervalMs = 2500) {
  const [events, setEvents] = useState<LogEvent[]>([])
  const sinceId = useRef(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    sinceId.current = 0
    setEvents([])

    async function poll() {
      try {
        const next = await api.getLogs(projectId!, sinceId.current)
        if (next.length && !cancelled) {
          sinceId.current = next[next.length - 1].id
          setEvents((prev) => [...prev, ...next])
        }
      } catch {
        // transient network hiccups shouldn't blow away the existing feed
      }
    }

    poll()
    const timer = setInterval(poll, intervalMs)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectId, intervalMs])

  return events
}

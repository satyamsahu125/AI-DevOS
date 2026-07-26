import { useEffect, useRef, useState } from "react"

import { api, type LogEvent } from "@/lib/api"

const POLL_INTERVAL_MS = 5000

/**
 * Fetches GET /projects/{projectId}/logs on mount and then polls every 5 s.
 *
 * FIX-E: The original hook fetched once and stopped, relying entirely on
 * WebSocket events for new entries. With WebSocket offline (or before it
 * reconnects) the Live Logs panel was frozen. We now maintain a sinceId
 * cursor and append new entries on each poll — WebSocket events still update
 * liveLogs in ProjectWorkspace directly, so there is no double-display.
 */
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
          setEvents((prev) => {
            // Deduplicate: if sinceId was 0 (first load), replace entirely;
            // otherwise append only the new entries.
            const existingIds = new Set(prev.map((e) => e.id))
            const incoming = next.filter((e) => !existingIds.has(e.id))
            return incoming.length ? [...prev, ...incoming] : prev
          })
        }
      } catch {
        // ignore transient network errors
      }
    }

    fetchLogs()
    const id = setInterval(fetchLogs, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [projectId])

  return events
}

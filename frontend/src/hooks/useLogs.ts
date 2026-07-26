import { useEffect, useRef, useState } from "react"
import { api, type LogEvent } from "../lib/api"

const POLL_MS = 5000

export function useLogs(projectId: string | null) {
  const [events, setEvents] = useState<LogEvent[]>([])
  const cursor = useRef(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    cursor.current = 0
    setEvents([])

    async function poll() {
      try {
        const next = await api.getLogs(projectId!, cursor.current)
        if (!cancelled && next.length) {
          cursor.current = next[next.length - 1].id
          setEvents(prev => {
            const ids = new Set(prev.map(e => e.id))
            const fresh = next.filter(e => !ids.has(e.id))
            return fresh.length ? [...prev, ...fresh] : prev
          })
        }
      } catch { /* ignore */ }
    }

    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [projectId])

  return events
}

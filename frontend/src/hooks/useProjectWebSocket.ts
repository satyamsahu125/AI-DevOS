import { useCallback, useEffect, useRef, useState } from "react"

export type WSMessage = {
  type: string
  timestamp: string
  stage?: string
  message?: string
  attempt?: number
  file_path?: string
  state?: string
  stages_completed?: string[]
  current_stage?: string
  line?: string
  level?: string
  [key: string]: unknown
}

type MessageHandler = (msg: WSMessage) => void

export function useProjectWebSocket(
  projectId: string | null,
  onMessage: MessageHandler
) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const reconnectDelay = useRef(1000)

  const connect = useCallback(() => {
    if (!projectId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const url = `${protocol}//${window.location.host}/api/ws/${projectId}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      reconnectDelay.current = 1000
    }

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        if (msg.type === "ping") {
          ws.send(JSON.stringify({ type: "ping" }))
          return
        }
        onMessage(msg)
      } catch (e) {
        console.warn("WebSocket parse error:", e)
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      // Reconnect with backoff (max 10s)
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, 10000)
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [projectId, onMessage])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  return { connected }
}

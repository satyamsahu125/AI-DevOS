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
  reason?: string
  duration_seconds?: number
  feedback?: string
  question?: string
  [key: string]: unknown
}

type MessageHandler = (msg: WSMessage) => void

export function useWebSocket(projectId: string | null, onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const delayRef = useRef(1000)
  const handlerRef = useRef(onMessage)
  handlerRef.current = onMessage

  const connect = useCallback(() => {
    if (!projectId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ws/${projectId}`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      delayRef.current = 1000
    }

    ws.onmessage = (ev) => {
      try {
        const msg: WSMessage = JSON.parse(ev.data)
        if (msg.type === "ping") { ws.send(JSON.stringify({ type: "ping" })); return }
        handlerRef.current(msg)
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      timerRef.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 1.5, 15000)
        connect()
      }, delayRef.current)
    }

    ws.onerror = () => ws.close()
  }, [projectId])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { connected }
}

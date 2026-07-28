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

interface WSOptions {
  onDisconnect?: () => void   // called immediately when WS drops
  onReconnect?: () => void    // called when WS comes back up
}

export function useWebSocket(
  projectId: string | null,
  onMessage: MessageHandler,
  opts?: WSOptions,
) {
  const wsRef      = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const timerRef   = useRef<number | undefined>(undefined)
  const delayRef   = useRef(300)           // start at 300ms, not 1 s
  const handlerRef = useRef(onMessage)
  const optsRef    = useRef(opts)
  handlerRef.current = onMessage
  optsRef.current    = opts

  const connect = useCallback(() => {
    if (!projectId) return
    // Guard against both OPEN and CONNECTING — React Strict Mode's double-effect
    // would otherwise create two sockets (the first in CLOSING state passes the
    // OPEN-only guard, causing every event to be received and logged twice).
    const state = wsRef.current?.readyState
    if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    const ws = new WebSocket(`${proto}//${window.location.host}/api/ws/${projectId}`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      delayRef.current = 300               // reset on successful connect
      optsRef.current?.onReconnect?.()
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
      optsRef.current?.onDisconnect?.()   // notify caller immediately
      timerRef.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 2, 8000)  // cap at 8 s
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

import { useCallback, useEffect, useRef, useState } from "react"

interface UseResizableOptions {
  /** "width" grows as the pointer moves right, "height" grows as it moves down -- pass invert to flip that. */
  axis: "width" | "height"
  initial: number
  min?: number
  max?: number
  /** Flip the drag direction (e.g. a handle on the left edge of a right-hand panel: dragging left should grow it). */
  invert?: boolean
  storageKey?: string
}

/** Tracks a panel's width/height in px, resizable by dragging a handle, optionally persisted across reloads. */
export function useResizable({ axis, initial, min = 160, max = 900, invert = false, storageKey }: UseResizableOptions) {
  const [size, setSize] = useState(() => {
    if (storageKey) {
      const stored = window.localStorage.getItem(storageKey)
      if (stored) {
        const parsed = Number(stored)
        if (!Number.isNaN(parsed)) return parsed
      }
    }
    return initial
  })
  const dragState = useRef<{ startPos: number; startSize: number } | null>(null)

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      dragState.current = {
        startPos: axis === "width" ? event.clientX : event.clientY,
        startSize: size,
      }
      event.preventDefault()
    },
    [axis, size],
  )

  useEffect(() => {
    function handleMove(event: PointerEvent) {
      if (!dragState.current) return
      const pos = axis === "width" ? event.clientX : event.clientY
      const delta = pos - dragState.current.startPos
      const signedDelta = invert ? -delta : delta
      const next = Math.min(max, Math.max(min, dragState.current.startSize + signedDelta))
      setSize(next)
    }
    function handleUp() {
      if (dragState.current && storageKey) {
        window.localStorage.setItem(storageKey, String(size))
      }
      dragState.current = null
    }
    window.addEventListener("pointermove", handleMove)
    window.addEventListener("pointerup", handleUp)
    return () => {
      window.removeEventListener("pointermove", handleMove)
      window.removeEventListener("pointerup", handleUp)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [axis, invert, min, max, storageKey, size])

  return { size, onPointerDown }
}

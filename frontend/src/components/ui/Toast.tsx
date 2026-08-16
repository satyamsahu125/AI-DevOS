/**
 * Toast notification system.
 *
 * Two APIs:
 *   1. addToast({ filename, type: "file" })  — standalone function, callable anywhere
 *      (WorkspacePage already uses this)
 *   2. useToast().push({ kind, title, message })  — hook for components inside ToastProvider
 *
 * Architecture: module-level event bus (subscriber list).
 * ToastProvider subscribes on mount and renders the queue.
 * addToast() pushes to subscribers without needing React context.
 */
import { useState, useEffect, ReactNode } from "react"
import { motion, AnimatePresence } from "framer-motion"

// ── Types ─────────────────────────────────────────────────────────────────────
export type ToastKind = "info" | "success" | "warning" | "error" | "file"

export interface ToastItem {
  id: string
  kind: ToastKind
  title: string
  message?: string
}

// ── Payload shapes ────────────────────────────────────────────────────────────
type FilePayload    = { type: "file"; filename: string }
type GenericPayload = { type?: never; kind: ToastKind; title: string; message?: string }
type AddToastPayload = FilePayload | GenericPayload

// ── Event bus ─────────────────────────────────────────────────────────────────
let _idCounter = 0
const nextId = () => String(++_idCounter)
const _subscribers: Array<(t: ToastItem) => void> = []

/**
 * Standalone toast trigger — importable anywhere, no context needed.
 * WorkspacePage calls: addToast({ filename, type: "file" })
 */
export function addToast(payload: AddToastPayload) {
  let item: ToastItem

  if (payload.type === "file") {
    item = {
      id: nextId(),
      kind: "file",
      title: "File written",
      message: payload.filename,
    }
  } else {
    item = {
      id: nextId(),
      kind: payload.kind,
      title: payload.title,
      message: payload.message,
    }
  }

  _subscribers.forEach(fn => fn(item))
}

// ── Color map ─────────────────────────────────────────────────────────────────
const KIND_STYLES: Record<ToastKind, { icon: string; accent: string; bg: string; border: string }> = {
  info:    { icon: "ℹ",  accent: "#7C3AED", bg: "rgba(124,58,237,0.12)",  border: "rgba(124,58,237,0.3)"  },
  success: { icon: "✓",  accent: "#10B981", bg: "rgba(16,185,129,0.12)",  border: "rgba(16,185,129,0.3)"  },
  warning: { icon: "⚠",  accent: "#F59E0B", bg: "rgba(245,158,11,0.12)",  border: "rgba(245,158,11,0.3)"  },
  error:   { icon: "✕",  accent: "#F43F5E", bg: "rgba(244,63,94,0.12)",   border: "rgba(244,63,94,0.3)"   },
  file:    { icon: "📄", accent: "#06B6D4", bg: "rgba(6,182,212,0.10)",   border: "rgba(6,182,212,0.25)"  },
}

// ── Single toast card ─────────────────────────────────────────────────────────
function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const s = KIND_STYLES[toast.kind]
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -12, scale: 0.94, transition: { duration: 0.18 } }}
      transition={{ type: "spring", stiffness: 280, damping: 26 }}
      onClick={onDismiss}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "12px 14px",
        borderRadius: 10,
        background: "rgba(15,15,28,0.96)",
        border: `1px solid ${s.border}`,
        boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px ${s.border}`,
        backdropFilter: "blur(12px)",
        minWidth: 260,
        maxWidth: 340,
        cursor: "pointer",
        userSelect: "none" as const,
      }}
    >
      {/* Kind icon */}
      <span style={{
        width: 22, height: 22, borderRadius: 6, flexShrink: 0,
        display: "grid", placeItems: "center",
        background: s.bg,
        fontSize: 11,
        color: s.accent,
        marginTop: 1,
      }}>
        {s.icon}
      </span>

      {/* Text */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#f0f0f2", lineHeight: 1.3 }}>
          {toast.title}
        </div>
        {toast.message && (
          <div style={{
            fontSize: 11,
            color: "rgba(255,255,255,0.45)",
            marginTop: 3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontFamily: toast.kind === "file" ? "monospace" : undefined,
          }}>
            {toast.message}
          </div>
        )}
      </div>

      {/* Dismiss ×  */}
      <button
        onClick={e => { e.stopPropagation(); onDismiss() }}
        style={{
          background: "none", border: "none", cursor: "pointer",
          color: "rgba(255,255,255,0.3)", fontSize: 14, lineHeight: 1,
          padding: 0, marginTop: 1, flexShrink: 0,
        }}
      >×</button>
    </motion.div>
  )
}

// ── Provider ──────────────────────────────────────────────────────────────────
const AUTO_DISMISS_MS = 4500

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    // Subscribe to the module-level event bus
    const handler = (item: ToastItem) => {
      setToasts(prev => [...prev, item])
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== item.id))
      }, AUTO_DISMISS_MS)
    }
    _subscribers.push(handler)
    return () => {
      const i = _subscribers.indexOf(handler)
      if (i >= 0) _subscribers.splice(i, 1)
    }
  }, [])

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <>
      {children}

      {/* Toast stack — fixed, bottom-right */}
      <div style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        pointerEvents: "none",
      }}>
        <AnimatePresence mode="sync">
          {toasts.map(t => (
            <div key={t.id} style={{ pointerEvents: "auto" }}>
              <ToastCard toast={t} onDismiss={() => dismiss(t.id)} />
            </div>
          ))}
        </AnimatePresence>
      </div>
    </>
  )
}

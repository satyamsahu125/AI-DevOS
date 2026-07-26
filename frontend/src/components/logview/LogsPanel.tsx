import { useEffect, useRef, useState } from "react"
import { type LogEvent } from "../../lib/api"

interface LogsPanelProps {
  events: LogEvent[]
  liveLogs: string[]
}

export function LogsPanel({ events, liveLogs }: LogsPanelProps) {
  const [tab, setTab] = useState<"structured" | "raw">("raw")
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events, liveLogs, autoScroll])

  const levelColor = (level: string) =>
    level === "error" ? "text-rose-400" : level === "warning" ? "text-amber-400" : "text-zinc-400"

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-zinc-800/60 bg-zinc-900/40 px-3 py-1.5">
        <div className="flex gap-1">
          {(["raw", "structured"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded px-2.5 py-1 text-[11px] font-medium ${tab === t ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
              {t === "raw" ? "Live" : "Events"}
            </button>
          ))}
        </div>
        <button
          onClick={() => setAutoScroll(a => !a)}
          className={`text-[10px] ${autoScroll ? "text-indigo-400" : "text-zinc-600"}`}
        >
          {autoScroll ? "⏬ auto-scroll" : "⏸ paused"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 font-mono text-[11px] space-y-0.5" onScroll={() => {}}>
        {tab === "raw" ? (
          liveLogs.length === 0 ? (
            <p className="py-8 text-center text-zinc-600">No live logs yet…</p>
          ) : (
            liveLogs.map((line, i) => (
              <div key={i} className={`leading-5 ${
                line.startsWith("✗") ? "text-rose-400" :
                line.startsWith("✓") ? "text-emerald-400" :
                line.startsWith("▶") ? "text-indigo-400" :
                line.startsWith("📄") ? "text-violet-400" :
                line.startsWith("↩") ? "text-amber-400" :
                "text-zinc-500"
              }`}>
                {line || " "}
              </div>
            ))
          )
        ) : (
          events.length === 0 ? (
            <p className="py-8 text-center text-zinc-600">No events yet…</p>
          ) : (
            events.map(ev => (
              <div key={ev.id} className="flex gap-2 leading-5">
                <span className="shrink-0 text-zinc-700">
                  {new Date(ev.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
                <span className="shrink-0 text-zinc-600">[{ev.stage}]</span>
                <span className={levelColor(ev.level)}>{ev.message}</span>
              </div>
            ))
          )
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from "react"
import { api, type LogEvent, STAGES, STAGE_LABELS, type StageName } from "../../lib/api"
import { type PipelineState } from "../../hooks/usePipeline"
import { Spinner } from "../ui/Spinner"

interface Message {
  role: "user" | "assistant"
  text: string
  meta?: string
}

interface ChatPanelProps {
  projectId: string
  logEvents: LogEvent[]
  liveLogs: string[]
  pipelineState: PipelineState
  onRetryStage: (stage: string) => Promise<void>
  onSubmitChange: (description: string) => Promise<unknown>
}

export function ChatPanel({ projectId, logEvents, liveLogs, pipelineState, onRetryStage, onSubmitChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [showRetry, setShowRetry] = useState(false)
  const [showChange, setShowChange] = useState(false)
  const [changeDraft, setChangeDraft] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, liveLogs])

  async function send(text: string) {
    if (!text.trim()) return
    setMessages(m => [...m, { role: "user", text }])
    setInput("")
    setSending(true)
    try {
      const res = await api.sendChat(projectId, text)
      setMessages(m => [...m, {
        role: "assistant",
        text: res.reply,
        meta: res.action_taken ? `Action: ${res.action_taken}${res.stage_triggered ? ` → ${res.stage_triggered}` : ""}` : undefined,
      }])
    } catch (err) {
      setMessages(m => [...m, { role: "assistant", text: err instanceof Error ? err.message : "Request failed." }])
    } finally {
      setSending(false)
    }
  }

  async function submitChange() {
    if (!changeDraft.trim()) return
    setSending(true)
    try {
      await onSubmitChange(changeDraft.trim())
      setChangeDraft("")
      setShowChange(false)
      setMessages(m => [...m, {
        role: "assistant",
        text: "Requirement change submitted. The pipeline will re-run affected stages.",
      }])
    } finally {
      setSending(false)
    }
  }

  const isActive = pipelineState.status === "running"
  const isFailed = pipelineState.status === "failed"

  return (
    <div className="flex flex-1 flex-col overflow-hidden">

      {/* Status bar */}
      {(isActive || isFailed) && (
        <div className={`shrink-0 border-b px-6 py-2.5 text-xs flex items-center justify-between ${
          isFailed
            ? "border-rose-500/20 bg-rose-500/5 text-rose-400"
            : "border-indigo-500/20 bg-indigo-500/5 text-indigo-300"
        }`}>
          <div className="flex items-center gap-2">
            {isActive && <Spinner size={12} className={isFailed ? "text-rose-400" : "text-indigo-400"} />}
            <span>
              {isFailed
                ? `Failed at: ${pipelineState.failed_stage?.replace(/_/g, " ") ?? "unknown stage"}`
                : `Running: ${pipelineState.current_stage?.replace(/_/g, " ") ?? "…"}`}
            </span>
          </div>
          <div className="flex gap-2">
            {isFailed && (
              <button onClick={() => setShowRetry(true)} className="rounded border border-rose-500/30 px-2 py-0.5 hover:bg-rose-500/10">
                Retry stage
              </button>
            )}
            <button onClick={() => setShowChange(true)} className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-400 hover:bg-zinc-800">
              Change request
            </button>
          </div>
        </div>
      )}

      {/* Live log stream */}
      {liveLogs.length > 0 && (
        <div className="shrink-0 border-b border-zinc-800/40 bg-zinc-950/50 px-5 py-2 font-mono max-h-36 overflow-y-auto text-[10px] text-zinc-500 scrollbar-none">
          {liveLogs.slice(-30).map((line, i) => (
            <div key={i} className={line.startsWith("✗") ? "text-rose-400" : line.startsWith("✓") ? "text-emerald-400" : line.startsWith("▶") ? "text-indigo-400" : ""}>
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {messages.length === 0 && logEvents.length === 0 && (
          <div className="flex h-32 items-center justify-center text-sm text-zinc-600">
            Chat with the AI about your project, artifacts, or pipeline status.
          </div>
        )}

        {/* Log events as timeline */}
        {logEvents.slice(-20).map(ev => (
          <div key={ev.id} className="flex gap-3 items-start">
            <span className={`mt-0.5 text-[10px] shrink-0 font-mono ${
              ev.level === "error" ? "text-rose-500" : ev.level === "warning" ? "text-amber-500" : "text-zinc-600"
            }`}>[{ev.stage}]</span>
            <p className="text-xs text-zinc-400 leading-relaxed">{ev.message}</p>
          </div>
        ))}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
              m.role === "user"
                ? "bg-indigo-600 text-white rounded-br-sm"
                : "bg-zinc-800/80 text-zinc-200 rounded-bl-sm"
            }`}>
              <p className="leading-relaxed whitespace-pre-wrap">{m.text}</p>
              {m.meta && <p className="mt-1.5 text-[10px] opacity-60">{m.meta}</p>}
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm bg-zinc-800/80 px-4 py-3">
              <Spinner size={14} className="text-zinc-400" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-zinc-800/60 p-4">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && input.trim()) { e.preventDefault(); send(input) } }}
            placeholder="Ask about the project, artifacts, or request changes…"
            className="flex-1 rounded-xl border border-zinc-700 bg-zinc-800/60 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || sending}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            {sending ? <Spinner size={14} /> : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Retry modal */}
      {showRetry && (
        <RetryModal
          failedStage={pipelineState.failed_stage}
          onRetry={async (stage) => { setShowRetry(false); await onRetryStage(stage) }}
          onClose={() => setShowRetry(false)}
        />
      )}

      {/* Change request modal */}
      {showChange && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowChange(false)}>
          <div onClick={e => e.stopPropagation()} className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl">
            <h3 className="mb-4 font-semibold text-zinc-100">Request a Change</h3>
            <textarea
              autoFocus
              value={changeDraft}
              onChange={e => setChangeDraft(e.target.value)}
              rows={4}
              placeholder="Describe the requirement change…"
              className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500 mb-4"
            />
            <div className="flex gap-3">
              <button onClick={() => setShowChange(false)} className="flex-1 rounded-lg border border-zinc-700 py-2.5 text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
              <button
                onClick={submitChange}
                disabled={!changeDraft.trim() || sending}
                className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
              >
                {sending && <Spinner size={12} />} Submit Change
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Retry modal ───────────────────────────────────────────────────────────

function RetryModal({ failedStage, onRetry, onClose }: { failedStage: string | null; onRetry: (s: string) => void; onClose: () => void }) {
  const [stage, setStage] = useState(failedStage ?? "")

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl">
        <h3 className="mb-4 font-semibold text-zinc-100">Retry Stage</h3>
        <select
          value={stage}
          onChange={e => setStage(e.target.value)}
          className="mb-4 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 outline-none"
        >
          <option value="">Select stage…</option>
          {STAGES.map(s => <option key={s} value={s}>{STAGE_LABELS[s as StageName]}</option>)}
        </select>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-zinc-700 py-2.5 text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
          <button
            onClick={() => stage && onRetry(stage)}
            disabled={!stage}
            className="flex-1 rounded-lg bg-rose-600 py-2.5 text-sm font-medium text-white hover:bg-rose-500 disabled:opacity-40"
          >Retry</button>
        </div>
      </div>
    </div>
  )
}

import { useState, useMemo, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import { Loader2, ArrowRight, Sparkles, RefreshCw, CheckCircle2, AlertCircle, Bot, User, Paperclip } from "lucide-react"

import { STAGE_LABELS, type LogEvent } from "@/lib/api"
import { Badge } from "@/components/ui/badge"

interface StageBlock {
  stage: string
  events: LogEvent[]
}

function groupByStage(events: LogEvent[]): StageBlock[] {
  const blocks: StageBlock[] = []
  for (const event of events) {
    const last = blocks[blocks.length - 1]
    if (last && last.stage === event.stage) {
      last.events.push(event)
    } else {
      blocks.push({ stage: event.stage, events: [event] })
    }
  }
  return blocks
}

function blockOutcome(events: LogEvent[]): "running" | "approved" | "failed" {
  const last = events[events.length - 1]
  if (last.message.includes("approved")) return "approved"
  if (last.level === "error") return "failed"
  return "running"
}

interface ChatPanelProps {
  logs: LogEvent[]
  onRetryStage: (stage: string) => void
  onSendMessage?: (text: string) => void
}

const QUICK_PROMPTS = [
  "Add User Auth & JWT sessions",
  "Redesign UI layout with dark mode",
  "Run OWASP Security check",
  "Add boundary error tests",
]

export function ChatPanel({ logs, onRetryStage, onSendMessage }: ChatPanelProps) {
  const [input, setInput] = useState("")
  const [userMessages, setUserMessages] = useState<Array<{ text: string; time: string }>>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const blocks = useMemo(() => groupByStage(logs), [logs])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [blocks.length, userMessages.length])

  function handleSend() {
    if (!input.trim()) return
    const text = input.trim()
    setUserMessages((prev) => [...prev, { text, time: new Date().toLocaleTimeString() }])
    setInput("")
    if (onSendMessage) {
      onSendMessage(text)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-[#0A0A14] justify-between">
      {/* Messages Scroll Feed Centered Column */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6 w-full max-w-3xl mx-auto">
        {blocks.length === 0 && userMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
            <div className="w-14 h-14 rounded-2xl bg-aurora-subtle border border-violet-500/20 flex items-center justify-center shadow-glow-purple">
              <Sparkles className="size-7 text-violet-400" />
            </div>
            <div className="max-w-md">
              <h3 className="text-base font-semibold text-white/90 mb-1">AI DevOS Multi-Agent Assistant</h3>
              <p className="text-xs text-white/40 leading-relaxed">
                Type a prompt below or start the pipeline to see Strategic Review, Architect, Designer, Developers, and QA work live.
              </p>
            </div>
          </div>
        )}

        {/* Combined Conversation Feed */}
        {userMessages.map((msg, idx) => (
          <motion.div
            key={`user-${idx}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="flex items-start justify-end gap-3"
          >
            <div className="max-w-xl rounded-2xl rounded-tr-sm glass-card p-4 text-xs text-white/90 shadow-glass border border-white/10">
              <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
              <span className="block mt-1 text-[10px] text-white/40 text-right">{msg.time}</span>
            </div>
            <div className="w-7 h-7 rounded-full bg-violet-600/30 text-violet-300 border border-violet-500/40 flex items-center justify-center shrink-0">
              <User className="size-3.5" />
            </div>
          </motion.div>
        ))}

        {blocks.map((block, i) => {
          const outcome = blockOutcome(block.events)
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="flex items-start gap-3"
            >
              <div className="w-7 h-7 rounded-full bg-white/5 border border-white/10 text-violet-400 flex items-center justify-center shrink-0">
                <Bot className="size-3.5" />
              </div>
              <div className="flex-1 glass-card p-4 shadow-glass border border-white/10 rounded-2xl rounded-tl-sm">
                <div className="mb-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-semibold text-white/90">
                    {outcome === "running" && <Loader2 className="size-3.5 animate-spin text-cyan-400" />}
                    {outcome === "approved" && <CheckCircle2 className="size-3.5 text-emerald-400" />}
                    {outcome === "failed" && <AlertCircle className="size-3.5 text-rose-400" />}
                    {STAGE_LABELS[block.stage as keyof typeof STAGE_LABELS] ?? block.stage} Agent
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={outcome === "approved" ? "success" : outcome === "failed" ? "destructive" : "warning"} className="text-[10px]">
                      {outcome === "approved" ? "Stage Complete" : outcome === "failed" ? "Failed" : "Processing…"}
                    </Badge>
                    {outcome === "failed" && (
                      <button onClick={() => onRetryStage(block.stage)} className="text-[10px] text-white/40 hover:text-white flex items-center gap-1 cursor-pointer">
                        <RefreshCw className="size-2.5" /> Retry
                      </button>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-1 font-mono text-[11px] leading-relaxed border-t border-white/10 pt-2.5">
                  {block.events.map((event) => (
                    <p
                      key={event.id}
                      className={
                        event.level === "error"
                          ? "text-rose-400"
                          : event.level === "warning"
                            ? "text-amber-400"
                            : "text-white/50"
                      }
                    >
                      &gt; {event.message}
                    </p>
                  ))}
                </div>
              </div>
            </motion.div>
          )
        })}

        <div ref={messagesEndRef} />
      </div>

      {/* Floating Message Input Box (Aurora Glass Style) */}
      <div className="border-t border-white/10 bg-black/20 backdrop-blur-glass p-4">
        {/* Suggestion chips */}
        <div className="flex gap-2 mb-3 overflow-x-auto scrollbar-none">
          {QUICK_PROMPTS.map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="flex-shrink-0 text-xs px-3 py-1.5 rounded-full glass-card hover:border-violet-500/30 hover:text-violet-300 hover:bg-violet-500/5 text-white/40 transition-all duration-200 whitespace-nowrap cursor-pointer"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input row */}
        <div className="glass-card flex items-end gap-3 p-3 aurora-border">
          <button className="text-white/30 hover:text-white/60 transition-colors pb-1 cursor-pointer" title="Attach context">
            <Paperclip size={16} />
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your instructions or chat with the AI team..."
            rows={1}
            className="flex-1 bg-transparent text-sm text-white/80 placeholder:text-white/25 outline-none resize-none max-h-32 py-1 leading-relaxed"
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSend}
            disabled={!input.trim()}
            className="w-8 h-8 rounded-lg bg-aurora flex items-center justify-center shadow-glow-purple flex-shrink-0 cursor-pointer disabled:opacity-40"
          >
            <ArrowRight size={14} className="text-white" />
          </motion.button>
        </div>
      </div>
    </div>
  )
}

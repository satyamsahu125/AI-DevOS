import { useEffect, useState, useCallback } from "react"
import { api, type QASession } from "../../lib/api"
import { Spinner } from "../ui/Spinner"

interface QAPanelProps {
  projectId: string
  onComplete: () => void
}

export function QAPanel({ projectId, onComplete }: QAPanelProps) {
  const [session, setSession] = useState<QASession | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [answer, setAnswer] = useState("")
  const [completing, setCompleting] = useState(false)

  const fetchSession = useCallback(async () => {
    try {
      const s = await api.getQASession(projectId)
      setSession(s as QASession)
      if ((s as QASession).is_complete && (s as QASession).answered > 0 && !completing) {
        setCompleting(true)
        const res = await api.completeQA(projectId)
        if (res.status !== "running") onComplete()
      }
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId, completing, onComplete])

  useEffect(() => {
    setLoading(true)
    fetchSession()
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function submitAnswer(text: string) {
    if (!text.trim() || !session?.current_question) return
    setSubmitting(true)
    try {
      const res = await api.answerQA(projectId, session.current_question.index, text.trim())
      setAnswer("")
      if (res.is_complete) {
        setCompleting(true)
        const cr = await api.completeQA(projectId)
        if (cr.status !== "running") onComplete()
      } else {
        await fetchSession()
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function skipQuestion() {
    if (!session?.current_question) return
    setSubmitting(true)
    try {
      const res = await api.skipQA(projectId, session.current_question.index)
      if (res.is_complete) {
        setCompleting(true)
        const cr = await api.completeQA(projectId)
        if (cr.status !== "running") onComplete()
      } else {
        await fetchSession()
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return (
    <div className="flex flex-1 items-center justify-center">
      <Spinner size={24} className="text-indigo-500" />
    </div>
  )

  if (completing || !session?.current_question) return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 ring-1 ring-emerald-500/20">
        <span className="text-2xl">✓</span>
      </div>
      <p className="font-medium text-zinc-200">Requirements clarified</p>
      <p className="text-sm text-zinc-500">Starting the AI pipeline...</p>
      <Spinner size={20} className="text-indigo-500" />
    </div>
  )

  const q = session.current_question
  const progress = session.total_questions > 0 ? session.answered / session.total_questions : 0
  const priorityBadge = q.priority === "CRITICAL" ? "text-rose-400 bg-rose-500/10 border-rose-500/20" : "text-zinc-500 bg-zinc-800 border-zinc-700"

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      {/* Header */}
      <div className="shrink-0 border-b border-zinc-800/60 px-8 py-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-medium text-indigo-400 uppercase tracking-wider">
            {q.category.replace(/_/g, " ")}
          </span>
          <span className="text-xs text-zinc-500 font-mono">
            {session.answered + 1} / {session.total_questions}
          </span>
        </div>
        {/* Progress */}
        <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 px-8 py-6 space-y-6">
        {/* Previous answers */}
        {session.previous_answers.slice(-2).map(prev => (
          <div key={prev.question_index} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 opacity-50">
            <p className="text-xs text-zinc-500 mb-1">{prev.question}</p>
            <p className="text-xs text-emerald-400 font-medium">✓ {prev.answer}</p>
          </div>
        ))}

        {/* Current question */}
        <div className="rounded-xl border border-indigo-500/20 bg-zinc-900/80 p-6 shadow-xl">
          {q.priority === "CRITICAL" && (
            <span className={`mb-3 inline-block rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${priorityBadge}`}>
              Critical
            </span>
          )}
          <p className="mb-5 text-sm font-medium leading-relaxed text-zinc-100">{q.question}</p>

          {/* Option buttons */}
          {q.options && q.options.length > 0 && (
            <div className="mb-4 grid gap-2">
              {q.options.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => submitAnswer(opt.label)}
                  disabled={submitting}
                  className="rounded-lg border border-zinc-700/60 bg-zinc-800/50 px-4 py-3 text-left text-sm text-zinc-300 transition hover:border-indigo-500/40 hover:bg-indigo-500/10 hover:text-zinc-100 disabled:opacity-40"
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}

          {/* Text input */}
          {(q.allows_custom || !q.options?.length) && (
            <div className="flex gap-2">
              <input
                autoFocus={!q.options?.length}
                value={answer}
                onChange={e => setAnswer(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && answer.trim()) submitAnswer(answer) }}
                placeholder={q.options?.length ? "Or type a custom answer…" : "Your answer…"}
                className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800/80 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
              />
              <button
                onClick={() => submitAnswer(answer)}
                disabled={!answer.trim() || submitting}
                className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40"
              >
                {submitting ? <Spinner size={14} /> : "→"}
              </button>
            </div>
          )}
        </div>

        {/* Skip */}
        {q.skippable && (
          <div className="flex justify-center">
            <button
              onClick={skipQuestion}
              disabled={submitting}
              className="text-xs text-zinc-600 hover:text-zinc-400 disabled:opacity-40"
            >
              Skip this question
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

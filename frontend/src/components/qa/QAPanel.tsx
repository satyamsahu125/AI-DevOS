import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowRight, SkipForward, CheckCircle2, Loader2 } from "lucide-react"

interface QAOption {
  value: string
  label: string
}

interface QAQuestion {
  index: number
  question: string
  category: string
  priority: string
  options: QAOption[] | null
  allows_custom: boolean
  skippable: boolean
}

interface QASessionData {
  project_id: string
  status: string
  total_questions: number
  answered: number
  current_question_index: number
  current_question: QAQuestion | null
  previous_answers: { question_index: number; question: string; answer: string }[]
  is_complete: boolean
}

interface QAPanelProps {
  projectId: string
  onComplete: () => void
}

export function QAPanel({ projectId, onComplete }: QAPanelProps) {
  const [session, setSession] = useState<QASessionData | null>(null)
  const [currentAnswer, setCurrentAnswer] = useState("")
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const fetchSession = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/workflow/${projectId}/qa`)
      const data = await res.json()
      setSession(data)
      if (data.is_complete && data.answered > 0) {
        await fetch(`/api/workflow/${projectId}/qa/complete`, { method: "POST" })
        onComplete()
      }
    } catch (e) {
      console.error("Failed to fetch QA session:", e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const submitAnswer = async (answerText: string) => {
    if (!answerText.trim() || !session?.current_question) return
    setSubmitting(true)

    try {
      const res = await fetch(`/api/workflow/${projectId}/qa/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_index: session.current_question.index,
          answer: answerText,
        }),
      })
      const data = await res.json()

      if (data.is_complete) {
        await fetch(`/api/workflow/${projectId}/qa/complete`, { method: "POST" })
        onComplete()
      } else {
        setCurrentAnswer("")
        await fetchSession()
      }
    } catch (e) {
      console.error("Failed to submit QA answer:", e)
    } finally {
      setSubmitting(false)
    }
  }

  const skipQuestion = async () => {
    if (!session?.current_question) return
    setSubmitting(true)
    try {
      const res = await fetch(`/api/workflow/${projectId}/qa/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_index: session.current_question.index,
        }),
      })
      const data = await res.json()
      if (data.is_complete) {
        await fetch(`/api/workflow/${projectId}/qa/complete`, { method: "POST" })
        onComplete()
      } else {
        setCurrentAnswer("")
        await fetchSession()
      }
    } catch (e) {
      console.error("Failed to skip QA question:", e)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading && !session) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="size-6 animate-spin text-indigo-500" />
      </div>
    )
  }

  if (!session || !session.current_question) {
    return (
      <div className="flex h-64 flex-col items-center justify-center p-6 text-center text-slate-400">
        <CheckCircle2 className="mb-2 size-8 text-emerald-400" />
        <p className="text-base font-medium text-slate-200">Requirements Clarified!</p>
        <p className="text-xs text-slate-400">Processing answers and starting downstream agents...</p>
      </div>
    )
  }

  const q = session.current_question
  const progress = session.total_questions > 0 ? session.answered / session.total_questions : 0

  return (
    <div className="mx-auto max-w-2xl p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
            Project Clarification ({q.category.replace(/_/g, " ")})
          </span>
          <span className="font-mono text-xs text-slate-400">
            Question {session.answered + 1} of {session.total_questions}
          </span>
        </div>
        {/* Progress bar */}
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-emerald-400"
            initial={{ width: 0 }}
            animate={{ width: `${progress * 100}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      </div>

      {/* Previous answers (last 2) */}
      {session.previous_answers && session.previous_answers.length > 0 && (
        <div className="mb-6 space-y-2">
          {session.previous_answers.slice(-2).map((prev) => (
            <div key={prev.question_index} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 opacity-60">
              <p className="text-xs text-slate-400">{prev.question}</p>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <CheckCircle2 size={13} />
                {prev.answer}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Current question card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={q.index}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.25 }}
          className="rounded-xl border border-indigo-500/20 bg-slate-900/80 p-6 shadow-xl backdrop-blur-md"
        >
          {q.priority === "CRITICAL" && (
            <span className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-rose-400">
              Critical Requirement
            </span>
          )}
          <h2 className="mb-4 text-base font-semibold text-slate-100">{q.question}</h2>

          {/* Option choices */}
          {q.options && q.options.length > 0 && (
            <div className="mb-4 grid grid-cols-1 gap-2">
              {q.options.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => submitAnswer(opt.label)}
                  disabled={submitting}
                  className="rounded-lg border border-white/10 bg-slate-800/50 px-4 py-3 text-left text-sm text-slate-300 transition-all hover:border-indigo-500/50 hover:bg-indigo-500/10 hover:text-white disabled:opacity-40"
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}

          {/* Custom text input */}
          {(q.allows_custom || !q.options || q.options.length === 0) && (
            <div className="mt-4 flex gap-2">
              <input
                value={currentAnswer}
                onChange={(e) => setCurrentAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && currentAnswer.trim()) {
                    submitAnswer(currentAnswer)
                  }
                }}
                placeholder={q.options ? "Or type a custom answer..." : "Type your answer..."}
                className="flex-1 rounded-lg border border-white/10 bg-slate-950 px-4 py-2.5 text-sm text-white placeholder:text-slate-500 outline-none focus:border-indigo-500"
                autoFocus
              />
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => submitAnswer(currentAnswer)}
                disabled={!currentAnswer.trim() || submitting}
                className="flex size-10 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-md shadow-indigo-600/30 hover:bg-indigo-500 disabled:opacity-40"
              >
                <ArrowRight size={16} />
              </motion.button>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Skip option */}
      {q.skippable && (
        <button
          onClick={skipQuestion}
          disabled={submitting}
          className="mx-auto flex items-center gap-1.5 text-xs text-slate-500 transition-colors hover:text-slate-300"
        >
          <SkipForward size={12} />
          Skip this question
        </button>
      )}
    </div>
  )
}

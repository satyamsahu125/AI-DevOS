import { useState } from "react"
import { api } from "../lib/api"
import { Spinner } from "./ui/Spinner"

export function ClarificationPanel({
  projectId,
  questions,
  onComplete,
}: {
  projectId: string
  questions: string[]
  onComplete: () => void
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleChange = (q: string, val: string) => {
    setAnswers(prev => ({ ...prev, [q]: val }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      await api.submitClarifications(projectId, answers)
      onComplete()
    } catch (err: any) {
      setError(err.message || "Failed to submit answers")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-2xl rounded-2xl border border-zinc-800 bg-zinc-900 p-8 shadow-2xl max-h-[90vh] overflow-y-auto"
      >
        <h2 className="mb-2 text-xl font-semibold text-zinc-100">The AI needs more information</h2>
        <p className="mb-6 text-sm text-zinc-400">
          Please answer the following questions to help the AI understand your requirements better.
        </p>

        {error && (
          <div className="mb-6 rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        <div className="space-y-6">
          {questions.map((q, idx) => (
            <div key={idx}>
              <label className="mb-2 block text-sm font-medium text-zinc-200">
                {q}
              </label>
              <textarea
                value={answers[q] || ""}
                onChange={e => handleChange(q, e.target.value)}
                placeholder="Type your answer here..."
                rows={3}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
              />
            </div>
          ))}
        </div>

        <div className="mt-8 flex gap-4">
          <button
            type="submit"
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-indigo-600 py-3 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading && <Spinner size={16} />}
            Submit Answers & Continue
          </button>
        </div>
      </form>
    </div>
  )
}

import { useEffect, useState } from "react"
import { api, type DesignReviewData } from "../../lib/api"
import { Spinner } from "../ui/Spinner"

interface Props {
  projectId: string
  onClose: () => void
  onActionCompleted: () => void
}

function renderValue(v: unknown, depth = 0): React.ReactNode {
  if (v === null || v === undefined) return <span className="text-zinc-600">—</span>
  if (typeof v === "string") return <span className="text-zinc-200">{v}</span>
  if (typeof v === "number" || typeof v === "boolean") return <span className="text-indigo-300">{String(v)}</span>
  if (Array.isArray(v)) return (
    <ul className="mt-1 space-y-1 pl-3">
      {v.map((item, i) => (
        <li key={i} className="flex gap-2 text-xs">
          <span className="text-zinc-600 shrink-0">•</span>
          <span>{renderValue(item, depth + 1)}</span>
        </li>
      ))}
    </ul>
  )
  if (typeof v === "object") return (
    <div className="mt-1 space-y-1 pl-3">
      {Object.entries(v as Record<string, unknown>).map(([k, val]) => (
        <div key={k} className={`flex gap-2 text-xs ${depth > 0 ? "border-l border-zinc-800 pl-2" : ""}`}>
          <span className="shrink-0 text-zinc-500">{k}:</span>
          <span>{renderValue(val, depth + 1)}</span>
        </div>
      ))}
    </div>
  )
  return <span className="text-zinc-200">{String(v)}</span>
}

export function DesignReviewModal({ projectId, onClose, onActionCompleted }: Props) {
  const [data, setData] = useState<DesignReviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [feedback, setFeedback] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<"spec" | "preview">("spec")
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    api.getDesignReview(projectId)
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [projectId])

  function loadPreview() {
    if (previewHtml) return
    setPreviewLoading(true)
    api.getDesignPreview(projectId)
      .then(r => { setPreviewHtml(r.html); setPreviewLoading(false) })
      .catch(() => { setPreviewHtml("<p style='padding:20px;color:#888'>Preview unavailable.</p>"); setPreviewLoading(false) })
  }

  function handleViewMode(mode: "spec" | "preview") {
    setViewMode(mode)
    if (mode === "preview") loadPreview()
  }

  async function approve() {
    setSubmitting(true)
    try {
      await api.postDesignReview(projectId, true, feedback || undefined)
      await api.continueWorkflow(projectId)
      onActionCompleted()
    } finally {
      setSubmitting(false)
    }
  }

  async function reject() {
    if (!feedback.trim()) return
    setSubmitting(true)
    try {
      await api.postDesignReview(projectId, false, feedback)
      onActionCompleted()
    } finally {
      setSubmitting(false)
    }
  }

  const design = data?.design ?? {}
  const sections = Object.entries(design)

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-6">
      <div className="w-full max-w-4xl rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl my-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-8 py-5">
          <div>
            <h2 className="text-base font-semibold text-zinc-100">Design Review</h2>
            {data && <p className="mt-0.5 text-xs text-zinc-500">Iteration {data.review_iteration} · {data.state}</p>}
          </div>
          <button onClick={onClose} className="text-zinc-600 hover:text-zinc-300 text-lg leading-none">✕</button>
        </div>

        {loading ? (
          <div className="flex h-64 items-center justify-center"><Spinner size={28} className="text-indigo-500" /></div>
        ) : (
          <>
            {/* Instructions */}
            {data?.instructions && (
              <div className="border-b border-zinc-800 bg-indigo-500/5 px-8 py-3">
                <p className="text-xs text-indigo-300">{data.instructions}</p>
              </div>
            )}

            {/* View mode tabs */}
            <div className="border-b border-zinc-800 px-8 pt-3 flex gap-1">
              {(["spec", "preview"] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => handleViewMode(mode)}
                  className={`px-4 py-1.5 text-xs rounded-t-md border-b-2 capitalize transition-colors ${
                    viewMode === mode
                      ? "border-indigo-500 text-indigo-300 bg-indigo-500/5"
                      : "border-transparent text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {mode === "spec" ? "Design Spec" : "Visual Preview"}
                </button>
              ))}
            </div>

            {/* Preview iframe */}
            {viewMode === "preview" && (
              <div className="overflow-hidden" style={{ height: "55vh" }}>
                {previewLoading ? (
                  <div className="flex h-full items-center justify-center"><Spinner size={28} className="text-indigo-500" /></div>
                ) : (
                  <iframe
                    srcDoc={previewHtml ?? ""}
                    sandbox="allow-same-origin"
                    title="Design Preview"
                    style={{ width: "100%", height: "100%", border: "none", background: "#0f0f0f" }}
                  />
                )}
              </div>
            )}

            {/* Design spec sections */}
            {viewMode === "spec" && (
            <div className="divide-y divide-zinc-800/60 overflow-y-auto max-h-[55vh]">
              {sections.length === 0 ? (
                <p className="px-8 py-6 text-sm text-zinc-500">No design data available.</p>
              ) : sections.map(([key, value]) => (
                <div key={key} className="px-8 py-4">
                  <button
                    onClick={() => setActiveSection(activeSection === key ? null : key)}
                    className="flex w-full items-center justify-between text-left"
                  >
                    <span className="text-sm font-medium text-zinc-200 capitalize">{key.replace(/_/g, " ")}</span>
                    <span className="text-xs text-zinc-600">{activeSection === key ? "▲" : "▼"}</span>
                  </button>
                  {activeSection === key && (
                    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-xs">
                      {renderValue(value)}
                    </div>
                  )}
                </div>
              ))}
            </div>
            )}

            {/* Feedback + actions */}
            <div className="border-t border-zinc-800 px-8 py-5 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                  Feedback (optional for approval, required for revision)
                </label>
                <textarea
                  value={feedback}
                  onChange={e => setFeedback(e.target.value)}
                  rows={3}
                  placeholder="Add comments or revision requests..."
                  className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800/60 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={reject}
                  disabled={!feedback.trim() || submitting}
                  className="flex items-center gap-2 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                >
                  {submitting && <Spinner size={12} />}
                  Request Revision
                </button>
                <button
                  onClick={approve}
                  disabled={submitting}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                >
                  {submitting && <Spinner size={12} />}
                  ✓ Approve & Start Coding
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

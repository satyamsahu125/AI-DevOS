import { useEffect, useState } from "react"
import { api, STAGES, STAGE_LABELS, type StageName, type ArtifactDetail, type ArtifactHistoryItem } from "../../lib/api"
import { Spinner } from "../ui/Spinner"

interface Props {
  projectId: string
  completedStages: string[]
}

export function ArtifactsPanel({ projectId, completedStages }: Props) {
  const [selected, setSelected] = useState<StageName | null>(null)
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null)
  const [history, setHistory] = useState<ArtifactHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [tab, setTab] = useState<"content" | "structured" | "history">("content")

  const completed = new Set(completedStages.map(s => s.toLowerCase()))
  const available = STAGES.filter(s => completed.has(s.toLowerCase()))

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    Promise.all([
      api.getArtifact(projectId, selected),
      api.getArtifactHistory(projectId, selected),
    ]).then(([a, h]) => {
      setArtifact(a)
      setHistory(h)
    }).catch(() => {
      setArtifact(null)
      setHistory([])
    }).finally(() => setLoading(false))
  }, [selected, projectId])

  return (
    <div className="flex h-full flex-col">
      {/* Stage selector */}
      <div className="shrink-0 overflow-x-auto border-b border-zinc-800/60 px-3 py-2 scrollbar-none">
        <div className="flex gap-1">
          {available.length === 0 ? (
            <p className="px-2 py-1 text-xs text-zinc-600">No artifacts yet</p>
          ) : available.map(s => (
            <button
              key={s}
              onClick={() => setSelected(s as StageName)}
              className={`shrink-0 rounded px-2.5 py-1 text-[11px] font-medium transition ${
                selected === s ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              }`}
            >
              {STAGE_LABELS[s as StageName]}
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <div className="flex shrink-0 gap-1 border-b border-zinc-800/60 px-3 py-1.5">
          {(["content", "structured", "history"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded px-2.5 py-1 text-[11px] ${tab === t ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
          {artifact && (
            <span className="ml-auto text-[10px] text-zinc-600">
              attempt {artifact.attempt}
            </span>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            Select a stage to view its artifact
          </div>
        ) : loading ? (
          <div className="flex h-full items-center justify-center"><Spinner size={20} className="text-indigo-500" /></div>
        ) : !artifact ? (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">No artifact available</div>
        ) : tab === "content" ? (
          <pre className="p-4 text-[11px] leading-relaxed text-zinc-300 font-mono whitespace-pre-wrap">
            {artifact.content}
          </pre>
        ) : tab === "structured" ? (
          <div className="p-4">
            {Object.keys(artifact.structured ?? {}).length === 0 ? (
              <p className="text-xs text-zinc-600">No structured data</p>
            ) : (
              <pre className="text-[11px] text-zinc-300 font-mono whitespace-pre-wrap">
                {JSON.stringify(artifact.structured, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/40 p-4 space-y-0">
            {history.length === 0 ? (
              <p className="text-xs text-zinc-600">No history</p>
            ) : history.map(h => (
              <div key={h.attempt} className="py-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${h.approved ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-500"}`}>
                    {h.approved ? "✓ approved" : `attempt ${h.attempt}`}
                  </span>
                </div>
                <pre className="text-[10px] text-zinc-500 font-mono whitespace-pre-wrap line-clamp-4">
                  {h.content?.slice(0, 300)}{(h.content?.length ?? 0) > 300 ? "…" : ""}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState } from "react"
import { api, type CostSummary, type MemorySummary, type AgentInfo } from "../../lib/api"
import { Spinner } from "../ui/Spinner"

interface Props { projectId: string }

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-4">
      <h4 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{title}</h4>
      {children}
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="flex items-start justify-between py-1.5 text-xs">
      <span className="text-zinc-500">{label}</span>
      <div className="text-right">
        <span className="font-mono text-zinc-200">{value}</span>
        {sub && <div className="text-[10px] text-zinc-600">{sub}</div>}
      </div>
    </div>
  )
}

export function MetricsPanel({ projectId }: Props) {
  const [cost, setCost] = useState<CostSummary | null>(null)
  const [memory, setMemory] = useState<MemorySummary | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<"cost" | "memory" | "agents">("cost")

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      api.getCost(projectId),
      api.getMemory(projectId),
      api.listAgents(),
    ]).then(([c, m, a]) => {
      if (c.status === "fulfilled") setCost(c.value)
      if (m.status === "fulfilled") setMemory(m.value)
      if (a.status === "fulfilled") setAgents(a.value)
    }).finally(() => setLoading(false))
  }, [projectId])

  const fmtMs = (ms: number) => ms >= 60000 ? `${(ms / 60000).toFixed(1)}m` : `${(ms / 1000).toFixed(1)}s`
  const fmtK  = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 gap-1 border-b border-zinc-800/60 px-3 py-1.5">
        {(["cost", "memory", "agents"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded px-2.5 py-1 text-[11px] capitalize ${tab === t ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}>
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <div className="flex h-32 items-center justify-center"><Spinner size={18} className="text-indigo-500" /></div>
        ) : tab === "cost" ? (
          cost ? (
            <>
              <Section title="Token usage">
                <Stat label="API calls" value={cost.calls} />
                <Stat label="Prompt tokens" value={fmtK(cost.prompt_tokens)} />
                <Stat label="Completion tokens" value={fmtK(cost.completion_tokens)} />
                <Stat label="Total tokens" value={fmtK(cost.total_tokens)} />
              </Section>
              <Section title="Latency">
                <Stat label="Total LLM time" value={fmtMs(cost.total_latency_ms)} />
                <Stat label="Avg per call" value={cost.calls > 0 ? fmtMs(cost.total_latency_ms / cost.calls) : "—"} />
              </Section>
            </>
          ) : <p className="text-xs text-zinc-600 text-center py-8">No cost data yet</p>
        ) : tab === "memory" ? (
          memory ? (
            <>
              <Section title="Memory store">
                <Stat label="Lessons" value={memory.lesson_count} />
                <Stat label="Trajectories" value={memory.trajectory_count} />
                <Stat label="Knowledge entries" value={memory.knowledge_entry_count} />
              </Section>
              {memory.records.length > 0 && (
                <Section title="Recent records">
                  <div className="space-y-2">
                    {memory.records.slice(0, 8).map((r, i) => (
                      <div key={i} className="rounded border border-zinc-800 bg-zinc-950/40 p-2.5">
                        <p className="text-[10px] font-mono text-zinc-500 truncate">{r.key}</p>
                        <p className="mt-1 text-[11px] text-zinc-400 line-clamp-2">{r.value_preview}</p>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </>
          ) : <p className="text-xs text-zinc-600 text-center py-8">No memory data yet</p>
        ) : (
          agents.length > 0 ? (
            <Section title="Registered agents">
              <div className="space-y-2">
                {agents.map((a, i) => (
                  <div key={i} className="flex items-start justify-between rounded border border-zinc-800 bg-zinc-950/40 p-2.5">
                    <div>
                      <p className="text-xs font-medium text-zinc-300">{a.agent}</p>
                      <p className="text-[10px] text-zinc-600">{a.stage}</p>
                    </div>
                    <span className={`rounded px-1.5 py-0.5 text-[9px] ${a.llm_backed ? "bg-indigo-500/10 text-indigo-400" : "bg-zinc-800 text-zinc-500"}`}>
                      {a.llm_backed ? "LLM" : "rule"}
                    </span>
                  </div>
                ))}
              </div>
            </Section>
          ) : <p className="text-xs text-zinc-600 text-center py-8">No agents registered</p>
        )}
      </div>
    </div>
  )
}

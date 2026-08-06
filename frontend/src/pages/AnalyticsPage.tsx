import { useEffect, useState } from "react"
import { api, type AnalyticsOverview, type AnalyticsLearning } from "../lib/api"
import { Spinner } from "../components/ui/Spinner"

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{
      background: "var(--color-surface)", border: "1px solid var(--color-divider)",
      borderRadius: 12, padding: "18px 20px",
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-muted)", letterSpacing: ".06em", textTransform: "uppercase", marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-.03em", color: "var(--color-text)" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: "var(--color-muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function Bar({ pct, color = "var(--color-accent)" }: { pct: number; color?: string }) {
  return (
    <div style={{ flex: 1, height: 6, background: "rgba(233,233,237,.08)", borderRadius: 3, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: color, borderRadius: 3, transition: "width .4s" }} />
    </div>
  )
}

export function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [learning, setLearning] = useState<AnalyticsLearning | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getAnalyticsOverview().catch(() => null),
      api.getLearningAnalytics().catch(() => null),
    ]).then(([ov, lrn]) => {
      setOverview(ov)
      setLearning(lrn)
    }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  const fmtTokens = (n: number) => n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}K` : String(n)
  const fmtMs = (ms: number) => ms >= 60000 ? `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s` : `${Math.round(ms / 1000)}s`

  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "28px 32px" }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-.03em", margin: 0 }}>Analytics</h1>
          <p style={{ color: "var(--color-muted)", fontSize: 13, margin: "6px 0 0" }}>
            Usage, cost, and learning intelligence across all projects
          </p>
        </div>

        {loading && (
          <div style={{ display: "flex", justifyContent: "center", paddingTop: 80 }}>
            <Spinner size={28} className="text-indigo-500" />
          </div>
        )}

        {error && (
          <div style={{ padding: "14px 18px", borderRadius: 10, background: "rgba(244,63,94,.08)", border: "1px solid rgba(244,63,94,.2)", color: "var(--color-error)", fontSize: 13 }}>
            {error}
          </div>
        )}

        {!loading && overview && (
          <>
            {/* Overview stats */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 14, marginBottom: 28 }}>
              <Stat label="Projects" value={overview.total_projects} />
              <Stat label="Stages Run" value={overview.total_stages_run.toLocaleString()} />
              <Stat label="Total Tokens" value={fmtTokens(overview.total_tokens)} />
              <Stat label="LLM Calls" value={overview.total_llm_calls.toLocaleString()} />
              <Stat label="Total Latency" value={fmtMs(overview.total_latency_ms)} />
              <Stat
                label="Avg Tokens / Project"
                value={fmtTokens(overview.avg_tokens_per_project)}
                sub="across all projects"
              />
            </div>

            {/* Stage breakdown */}
            {overview.stage_breakdown && overview.stage_breakdown.length > 0 && (
              <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-divider)", borderRadius: 12, padding: "20px 24px", marginBottom: 24 }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, color: "var(--color-text)" }}>
                  Stage Breakdown
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {overview.stage_breakdown.slice(0, 12).map(row => (
                    <div key={row.stage} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ width: 120, fontSize: 12, color: "var(--color-muted)", flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {row.stage.replace(/_/g, " ")}
                      </span>
                      <Bar pct={row.success_rate * 100} color={row.success_rate > 0.8 ? "var(--color-success)" : row.success_rate > 0.5 ? "var(--color-warning)" : "var(--color-error)"} />
                      <span style={{ fontSize: 11, color: "var(--color-muted)", flexShrink: 0, width: 40, textAlign: "right" }}>
                        {Math.round(row.success_rate * 100)}%
                      </span>
                      <span style={{ fontSize: 11, color: "var(--color-muted)", flexShrink: 0, width: 60, textAlign: "right" }}>
                        {fmtTokens(row.avg_tokens)} tok
                      </span>
                      <span style={{ fontSize: 11, color: "rgba(233,233,237,.3)", flexShrink: 0, width: 40, textAlign: "right" }}>
                        ×{row.calls}
                      </span>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 11, color: "var(--color-muted)" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--color-success)", display: "inline-block" }} /> &gt;80% success
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--color-warning)", display: "inline-block" }} /> 50–80%
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--color-error)", display: "inline-block" }} /> &lt;50%
                  </span>
                </div>
              </div>
            )}
          </>
        )}

        {/* Learning intelligence */}
        {!loading && learning && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            {/* Lessons */}
            <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-divider)", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>Learning Lessons</span>
                <span style={{ fontSize: 11, color: "var(--color-muted)", padding: "3px 8px", borderRadius: 6, background: "var(--color-accent-dim)", color: "var(--color-accent)" }}>
                  {learning.total_lessons} total
                </span>
              </div>
              {learning.recent_lessons.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--color-muted)", opacity: .5 }}>No lessons recorded yet</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {learning.recent_lessons.slice(0, 6).map(lesson => (
                    <div key={lesson.lesson_id} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)", flexShrink: 0, marginTop: 5 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: "var(--color-text)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {lesson.title || lesson.stage}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--color-muted)" }}>
                          {lesson.stage} · {new Date(lesson.created_at).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 12, fontSize: 12, color: "var(--color-muted)" }}>
                {learning.total_trajectories.toLocaleString()} trajectories recorded
              </div>
            </div>

            {/* Top patterns */}
            <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-divider)", borderRadius: 12, padding: "20px 24px" }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>Top Patterns</div>
              {learning.top_patterns.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--color-muted)", opacity: .5 }}>No patterns extracted yet</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {learning.top_patterns.slice(0, 6).map((p, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 11, color: "var(--color-muted)", width: 18, textAlign: "right", flexShrink: 0 }}>
                        {i + 1}.
                      </span>
                      <span style={{ flex: 1, fontSize: 12, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {p.pattern}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--color-accent)", padding: "2px 7px", borderRadius: 4, background: "var(--color-accent-dim)", flexShrink: 0 }}>
                        ×{p.count}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !overview && !error && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingTop: 80, gap: 16, opacity: .5 }}>
            <svg width="48" height="48" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 20V10M12 20V4M6 20v-6" />
            </svg>
            <div style={{ fontSize: 14, textAlign: "center" }}>
              No analytics data yet.<br />
              <span style={{ fontSize: 12, color: "var(--color-muted)" }}>Run some projects to see usage statistics here.</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

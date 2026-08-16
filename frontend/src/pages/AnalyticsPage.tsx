import { useEffect, useState } from "react"
import { api, type AnalyticsOverview, type AnalyticsLearning } from "../lib/api"

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="surface-2" style={{ padding: "14px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: "var(--text)", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

function SuccessBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100)
  const color = pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--error)"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: "var(--surface-3)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2, transition: "width 400ms ease" }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: "monospace", color, width: 34, textAlign: "right" }}>{pct}%</span>
    </div>
  )
}

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [learning, setLearning] = useState<AnalyticsLearning | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getAnalyticsOverview(),
      api.getLearningAnalytics(),
    ]).then(([o, l]) => {
      setOverview(o)
      setLearning(l)
      setLoading(false)
    }).catch(err => {
      setError(err.message ?? "Failed to load analytics")
      setLoading(false)
    })
  }, [])

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="page-header">
        <div className="page-title">Analytics</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Usage, performance, and learning intelligence</div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 28 }}>
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <div className="spinner spinner-lg" />
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        {overview && !loading && (
          <>
            {/* Overview stats */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Platform Overview</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10 }}>
                <StatCard label="Total Projects" value={overview.total_projects} />
                <StatCard label="Stages Run" value={overview.total_stages_run.toLocaleString()} />
                <StatCard label="Total Tokens" value={overview.total_tokens.toLocaleString()} />
                <StatCard label="LLM Calls" value={overview.total_llm_calls.toLocaleString()} />
                <StatCard
                  label="Total Latency"
                  value={`${(overview.total_latency_ms / 1000).toFixed(0)}s`}
                />
                <StatCard
                  label="Avg Tokens / Project"
                  value={Math.round(overview.avg_tokens_per_project).toLocaleString()}
                  sub="per project"
                />
              </div>
            </div>

            {/* Stage breakdown */}
            {overview.stage_breakdown && overview.stage_breakdown.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Stage Performance</div>
                <div className="surface" style={{ overflow: "hidden" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Stage</th>
                        <th>Calls</th>
                        <th>Avg Tokens</th>
                        <th>Success Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.stage_breakdown.map(s => (
                        <tr key={s.stage}>
                          <td className="td-primary" style={{ fontFamily: "monospace", fontSize: 12 }}>{s.stage}</td>
                          <td style={{ fontFamily: "monospace" }}>{s.calls}</td>
                          <td style={{ fontFamily: "monospace" }}>{Math.round(s.avg_tokens).toLocaleString()}</td>
                          <td style={{ minWidth: 140 }}><SuccessBar rate={s.success_rate} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {learning && !loading && (
          <>
            {/* Learning overview */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Learning Intelligence</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 16 }}>
                <StatCard label="Total Lessons" value={learning.total_lessons} sub="from approved trajectories" />
                <StatCard label="Trajectories" value={learning.total_trajectories} sub="recorded executions" />
              </div>

              {/* Top patterns */}
              {learning.top_patterns && learning.top_patterns.length > 0 && (
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Top Extracted Patterns</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {learning.top_patterns.map((p, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 12px", background: "var(--surface-1)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                        <span style={{ fontSize: 11, fontFamily: "monospace", color: "var(--text-dim)", width: 20 }}>#{i + 1}</span>
                        <span style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>{String(p.pattern)}</span>
                        <span className="badge badge-neutral" style={{ fontFamily: "monospace" }}>{p.count}×</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent lessons */}
              {learning.recent_lessons && learning.recent_lessons.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Recent Lessons</div>
                  <div className="surface" style={{ overflow: "hidden" }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Stage</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {learning.recent_lessons.map(lesson => (
                          <tr key={lesson.lesson_id}>
                            <td className="td-primary">{lesson.title}</td>
                            <td style={{ fontFamily: "monospace", fontSize: 12 }}>{lesson.stage}</td>
                            <td style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>
                              {new Date(lesson.created_at).toLocaleDateString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

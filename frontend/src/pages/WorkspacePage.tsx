import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  api, STAGES, STAGE_LABELS,
  type ProjectDetail, type CostSummary, type ProjectFiles,
  type LogEvent, type ArtifactSummary,
} from "../lib/api"
import { usePipeline } from "../hooks/usePipeline"
import { useLogs } from "../hooks/useLogs"
import { DesignReviewModal } from "../components/design/DesignReviewModal"
import { QAPanel } from "../components/qa/QAPanel"
import { ClarificationPanel } from "../components/ClarificationPanel"

// ── Icon primitives ──────────────────────────────────────────────────────────
function IcDone() {
  return <span style={{ width:12,height:12,borderRadius:"50%",background:"var(--color-accent)",display:"inline-block",flexShrink:0 }} />
}
function IcSpinner() {
  return <span style={{ width:14,height:14,borderRadius:"50%",border:"2px solid var(--color-divider)",borderTopColor:"var(--color-accent)",display:"inline-block",flexShrink:0,animation:"spin .8s linear infinite",boxSizing:"border-box" }} />
}
function IcPending() {
  return <span style={{ width:12,height:12,borderRadius:"50%",border:"1.5px solid currentColor",opacity:.3,display:"inline-block",flexShrink:0,boxSizing:"border-box" }} />
}
function IcDiamond() {
  return <span style={{ width:13,height:13,background:"var(--color-accent)",transform:"rotate(45deg)",borderRadius:3,display:"inline-block",flexShrink:0 }} />
}
function IcSquare({ color = "currentColor" }: { color?: string }) {
  return <span style={{ width:9,height:9,background:color,display:"inline-block",flexShrink:0 }} />
}
function IcTri() {
  return <span style={{ width:0,height:0,borderTop:"5px solid transparent",borderBottom:"5px solid transparent",borderLeft:"8px solid currentColor",display:"inline-block",flexShrink:0 }} />
}

// ── Stage sidebar ─────────────────────────────────────────────────────────────
function StageSidebar({
  completedStages, currentStage, failedStage,
}: { completedStages: string[]; currentStage: string | null; failedStage: string | null }) {
  const done = new Set(completedStages.map(s => s.toLowerCase()))

  return (
    <div style={{ padding:"16px 12px", borderRight:"1px solid var(--color-divider)", overflowY:"auto", display:"flex", flexDirection:"column" }}>
      <div className="ws-section-title">Pipeline</div>
      <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
        {STAGES.map(stage => {
          const key = stage.toLowerCase()
          const isDone    = done.has(key)
          const isRunning = currentStage?.toLowerCase() === key
          const isFailed  = failedStage?.toLowerCase() === key

          return (
            <div key={stage} className={`ws-stage-row${isRunning ? " running" : ""}`}>
              {isFailed   ? <IcDone /> /* show accent dot in red-ish */ :
               isDone     ? <IcDone /> :
               isRunning  ? <IcSpinner /> :
                            <IcPending />}
              <span style={{
                fontSize: 13,
                flex: 1,
                fontWeight: isRunning ? 600 : 400,
                opacity: isDone || isRunning || isFailed ? .7 : .35,
                color: isFailed ? "var(--color-error)" : undefined,
              }}>
                {STAGE_LABELS[stage]}
              </span>
              {isRunning && (
                <span style={{ fontSize:9, padding:"2px 7px", borderRadius:4, background:"rgba(233,233,237,.1)", border:"1px solid var(--color-divider)", whiteSpace:"nowrap" }}>
                  running
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Stat card ──────────────────────────────────────────────────────────────────
function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="ws-stat">
      <div className="ws-stat-label">{label}</div>
      <div className="ws-stat-value">{value}</div>
    </div>
  )
}

// ── Log panel ──────────────────────────────────────────────────────────────────
function LogPanel({ events, liveLogs, currentStage }: {
  events: LogEvent[]
  liveLogs: string[]
  currentStage: string | null
}) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events, liveLogs, autoScroll])

  const stageName = currentStage
    ? STAGE_LABELS[currentStage as keyof typeof STAGE_LABELS] ?? currentStage.replace(/_/g, " ")
    : "Pipeline"

  return (
    <div style={{ display:"flex", flexDirection:"column", overflow:"hidden", background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", flex:1, minHeight:0 }}>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", gap:8, padding:"10px 14px", borderBottom:"1px solid var(--color-divider)", flexShrink:0 }}>
        <IcSquare color="var(--color-accent)" />
        <span style={{ fontWeight:600, fontSize:13 }}>Live Log — {stageName}</span>
        <div style={{ display:"flex", alignItems:"center", gap:5, marginLeft:"auto", fontSize:11, opacity:.6 }}>
          <span style={{ width:6, height:6, borderRadius:"50%", background:"var(--color-accent)", animation:"pulse-o 1.4s ease-in-out infinite", display:"inline-block" }} />
          streaming
        </div>
        <button
          onClick={() => setAutoScroll(p => !p)}
          style={{ fontSize:10, padding:"2px 8px", borderRadius:4, border:"1px solid var(--color-divider)", background:autoScroll?"var(--color-accent-dim)":"transparent", color:autoScroll?"var(--color-accent)":"var(--color-muted)", cursor:"pointer" }}>
          auto-scroll
        </button>
      </div>

      {/* Lines */}
      <div style={{ flex:1, overflowY:"auto", padding:"12px 14px" }}>
        {events.length === 0 && liveLogs.length === 0 ? (
          <div style={{ opacity:.3, fontSize:12, textAlign:"center", marginTop:40 }}>No live logs yet…</div>
        ) : (
          <>
            {events.map(e => (
              <div key={e.id} className="ws-log-line">
                <span className="lt">{new Date(e.created_at).toLocaleTimeString("en", { hour:"2-digit", minute:"2-digit", second:"2-digit" })}</span>
                <span className="la">›</span>
                {e.message}
              </div>
            ))}
            {liveLogs.map((line, i) => (
              <div key={`live-${i}`} className="ws-log-line" style={{ opacity:.8 }}>
                <span className="la">›</span>{line}
              </div>
            ))}
          </>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Files panel ────────────────────────────────────────────────────────────────
function FilesPanel({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ProjectFiles | null>(null)

  useEffect(() => {
    api.getFiles(projectId).then(setFiles).catch(() => {})
  }, [projectId])

  if (!files || (files.backend.length === 0 && files.frontend.length === 0)) {
    return (
      <div style={{ background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:"12px 14px" }}>
        <div className="ws-section-title" style={{ marginBottom:6 }}>Files</div>
        <div style={{ fontSize:12, opacity:.3 }}>No files generated yet</div>
      </div>
    )
  }

  return (
    <div style={{ background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:"12px 14px" }}>
      <div className="ws-section-title" style={{ marginBottom:6 }}>Files</div>
      {files.backend.length > 0 && (
        <>
          <div style={{ fontSize:11, opacity:.55, letterSpacing:".03em", marginBottom:4 }}>backend/</div>
          {files.backend.slice(0, 4).map(f => (
            <div key={f} className="ws-file-item">
              <span style={{ width:7, height:7, borderRadius:1.5, background:"var(--color-accent)", display:"inline-block", flexShrink:0 }} />
              <span style={{ overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", opacity:.85 }}>{f}</span>
            </div>
          ))}
        </>
      )}
      {files.frontend.length > 0 && (
        <>
          <div style={{ fontSize:11, opacity:.55, letterSpacing:".03em", marginBottom:4, marginTop:8 }}>frontend/</div>
          {files.frontend.slice(0, 3).map(f => (
            <div key={f} className="ws-file-item" style={{ opacity:.55 }}>
              <span style={{ width:7, height:7, borderRadius:1.5, background:"currentColor", display:"inline-block", flexShrink:0 }} />
              <span style={{ overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{f}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// ── Chat panel ────────────────────────────────────────────────────────────────
function ChatPanel({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<{ role: "user"|"agent"; text: string }[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }) }, [messages])

  async function send() {
    if (!input.trim() || sending) return
    const text = input.trim()
    setInput("")
    setMessages(m => [...m, { role:"user", text }])
    setSending(true)
    try {
      const res = await api.sendChat(projectId, text)
      setMessages(m => [...m, { role:"agent", text: res.reply }])
    } catch {
      setMessages(m => [...m, { role:"agent", text: "Sorry, couldn't reach the agent." }])
    } finally { setSending(false) }
  }

  return (
    <div style={{ display:"flex", flexDirection:"column", background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:"12px 14px", flex:1, minHeight:0, overflow:"hidden" }}>
      <div className="ws-section-title" style={{ marginBottom:6 }}>Chat</div>

      <div style={{ flex:1, overflowY:"auto", display:"flex", flexDirection:"column", gap:8, marginBottom:8 }}>
        {messages.length === 0 && (
          <div style={{ fontSize:12, opacity:.3, textAlign:"center", marginTop:20 }}>Message the build…</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className="ws-chat-msg" style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            background: m.role === "user" ? "var(--color-accent-dim)" : "rgba(233,233,237,.06)",
            border: `1px solid ${m.role === "user" ? "var(--color-accent-border)" : "var(--color-divider)"}`,
            color: m.role === "user" ? "var(--color-accent)" : "var(--color-text)",
          }}>
            {m.text}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ display:"flex", gap:6, flexShrink:0 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Message the build…"
          style={{ flex:1, minHeight:32, padding:"5px 10px", fontSize:12.5, background:"var(--color-bg)", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", color:"var(--color-text)", fontFamily:"var(--font-sans)", outline:"none" }}
        />
        <button onClick={send} disabled={sending || !input.trim()}
          style={{ width:32, height:32, display:"grid", placeItems:"center", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", background:sending?"var(--color-accent-dim)":"transparent", cursor:"pointer", color:"var(--color-accent)", flexShrink:0 }}>
          <IcTri />
        </button>
      </div>
    </div>
  )
}

// ── Artifacts panel ───────────────────────────────────────────────────────────
function ArtifactsPanel({ artifacts }: { artifacts: ArtifactSummary[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const [content, setContent] = useState<Record<string, string>>({})

  function toggle(key: string, json?: string) {
    if (open === key) { setOpen(null); return }
    setOpen(key)
    if (json && !content[key]) setContent(p => ({ ...p, [key]: json }))
  }

  if (!artifacts || artifacts.length === 0) {
    return (
      <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", color:"var(--color-muted)", fontSize:13 }}>
        No artifacts yet — run the pipeline first.
      </div>
    )
  }

  return (
    <div style={{ flex:1, overflowY:"auto", padding:"0 4px" }}>
      <div className="ws-section-title" style={{ marginBottom:12 }}>Stage Artifacts</div>
      <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
        {artifacts.map((a, i) => {
          const key = `${a.stage}-${i}`
          const isOpen = open === key
          let preview = ""
          try { preview = a.json ? JSON.stringify(JSON.parse(a.json), null, 2).slice(0, 800) : "" } catch { preview = a.json ?? "" }
          return (
            <div key={key} style={{ background:"var(--color-surface)", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", overflow:"hidden" }}>
              <button onClick={() => toggle(key, a.json)}
                style={{ width:"100%", display:"flex", alignItems:"center", gap:10, padding:"10px 14px", background:"transparent", border:"none", cursor:"pointer", textAlign:"left", color:"var(--color-text)" }}>
                <IcDone />
                <span style={{ flex:1, fontSize:13, fontWeight:500 }}>{STAGE_LABELS[a.stage as keyof typeof STAGE_LABELS] ?? a.stage}</span>
                <span style={{ fontSize:11, opacity:.4 }}>attempt {a.attempt}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round"
                  style={{ opacity:.4, transform: isOpen ? "rotate(180deg)" : "none", transition:"transform .15s", flexShrink:0 }}>
                  <path d="M6 9l6 6 6-6"/>
                </svg>
              </button>
              {isOpen && (
                <pre style={{ margin:0, padding:"0 14px 12px", fontSize:11, lineHeight:1.55, overflowX:"auto", color:"rgba(233,233,237,.7)", fontFamily:"var(--font-mono)", maxHeight:360, overflowY:"auto" }}>
                  {preview || "(no structured content)"}
                  {preview.length >= 800 && <span style={{ opacity:.4 }}>\n… (truncated)</span>}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Integrations panel ────────────────────────────────────────────────────────
function IntegrationsPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<import("../lib/api").ProjectIntegrations | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getProjectIntegrations(projectId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) return (
    <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center" }}>
      <span style={{ width:20, height:20, borderRadius:"50%", border:"2px solid var(--color-divider)", borderTopColor:"var(--color-accent)", animation:"spin .8s linear infinite", display:"inline-block" }} />
    </div>
  )
  if (!data || data.detected_services.length === 0) return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:12, opacity:.4, textAlign:"center", padding:32 }}>
      <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1} strokeLinecap="round"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z M13 2v7h7" /></svg>
      <div style={{ fontSize:13 }}>No integrations detected yet.<br /><span style={{ fontSize:11, color:"var(--color-muted)" }}>Run the pipeline — the Integration agent will detect services from your project description.</span></div>
    </div>
  )
  return (
    <div style={{ flex:1, overflowY:"auto", padding:"0 4px" }}>
      <div className="ws-section-title" style={{ marginBottom:12 }}>Detected Integrations</div>
      <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
        {data.detected_services.map(svc => {
          const vars = data.env_vars_needed.filter(v => v.service === svc)
          return (
            <div key={svc} style={{ background:"var(--color-surface)", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", overflow:"hidden" }}>
              <div style={{ display:"flex", alignItems:"center", gap:8, padding:"10px 14px", borderBottom: vars.length ? "1px solid var(--color-divider)" : "none" }}>
                <span style={{ width:8, height:8, borderRadius:"50%", background:"var(--color-accent)", display:"inline-block", flexShrink:0 }} />
                <span style={{ fontSize:13, fontWeight:600, textTransform:"capitalize" }}>{svc.replace(/_/g, " ")}</span>
                <span style={{ marginLeft:"auto", fontSize:10, padding:"2px 7px", borderRadius:4, background:"var(--color-accent-dim)", color:"var(--color-accent)" }}>
                  {vars.length} env var{vars.length !== 1 ? "s" : ""}
                </span>
              </div>
              {vars.length > 0 && (
                <div style={{ padding:"8px 14px", display:"flex", flexDirection:"column", gap:4 }}>
                  {vars.map(v => (
                    <div key={v.var_name} style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <code style={{ fontSize:11, fontFamily:"var(--font-mono)", color: v.required ? "var(--color-text)" : "var(--color-muted)", flex:1 }}>{v.var_name}</code>
                      {v.required && <span style={{ fontSize:9, padding:"1px 6px", borderRadius:3, background:"rgba(244,63,94,.1)", color:"var(--color-error)", border:"1px solid rgba(244,63,94,.2)" }}>required</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Metrics panel ─────────────────────────────────────────────────────────────
function MetricsPanel({ cost, pipeline }: { cost: CostSummary | null; pipeline: { progress_percent: number; stages_completed: string[]; current_sprint: number; total_sprints: number; total_stages: number } }) {
  const rows: { label: string; value: string | number }[] = [
    { label: "LLM Calls",          value: cost?.calls ?? 0 },
    { label: "Prompt tokens",      value: cost?.prompt_tokens?.toLocaleString() ?? "—" },
    { label: "Completion tokens",  value: cost?.completion_tokens?.toLocaleString() ?? "—" },
    { label: "Total tokens",       value: cost?.total_tokens?.toLocaleString() ?? "—" },
    { label: "Total latency",
      value: cost ? `${(cost.total_latency_ms / 1000).toFixed(1)}s` : "—" },
    { label: "Stages completed",   value: `${pipeline.stages_completed.filter(s => STAGES.includes(s as any)).length} / ${pipeline.total_stages}` },
    { label: "Progress",           value: `${pipeline.progress_percent}%` },
    { label: "Sprint",
      value: pipeline.total_sprints > 0 ? `${pipeline.current_sprint} / ${pipeline.total_sprints}` : "—" },
  ]
  return (
    <div style={{ flex:1, overflowY:"auto", padding:"0 4px" }}>
      <div className="ws-section-title" style={{ marginBottom:12 }}>Metrics</div>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
        {rows.map(r => (
          <div key={r.label} style={{ background:"var(--color-surface)", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", padding:"12px 16px" }}>
            <div style={{ fontSize:11, opacity:.5, letterSpacing:".06em", textTransform:"uppercase", marginBottom:4 }}>{r.label}</div>
            <div style={{ fontSize:20, fontWeight:700, letterSpacing:"-.02em" }}>{r.value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Gate modal ────────────────────────────────────────────────────────────────
function GateModal({ projectId, gate, onDone }: { projectId: string; gate: string; onDone: () => void }) {
  const [feedback, setFeedback] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const gateLabel = gate === "architecture" ? "Architecture Review" : gate === "sprint_plan" ? "Sprint Plan Review" : gate

  async function approve() {
    setLoading(true); setError("")
    try { await api.approveGate(projectId, gate); onDone() }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Failed") }
    finally { setLoading(false) }
  }

  async function revise() {
    if (!feedback.trim()) { setError("Please provide feedback for revision"); return }
    setLoading(true); setError("")
    try { await api.reviseGate(projectId, gate, feedback.trim()); onDone() }
    catch (e: unknown) { setError(e instanceof Error ? e.message : "Failed") }
    finally { setLoading(false) }
  }

  return (
    <div style={{ position:"fixed", inset:0, zIndex:50, display:"flex", alignItems:"center", justifyContent:"center", background:"rgba(0,0,0,.6)", backdropFilter:"blur(4px)" }}>
      <div style={{ width:"100%", maxWidth:480, margin:16, background:"var(--color-surface)", border:"1px solid var(--color-divider)", borderRadius:16, padding:28, boxShadow:"0 24px 64px rgba(0,0,0,.5)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:20 }}>
          <span style={{ width:32, height:32, borderRadius:8, background:"rgba(245,158,11,.12)", border:"1px solid rgba(245,158,11,.25)", display:"grid", placeItems:"center" }}>
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="var(--color-warning)" strokeWidth={2} strokeLinecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z M12 9v4 M12 17h.01" /></svg>
          </span>
          <div>
            <div style={{ fontSize:15, fontWeight:700 }}>{gateLabel}</div>
            <div style={{ fontSize:12, color:"var(--color-muted)" }}>Review required before pipeline continues</div>
          </div>
        </div>

        <div style={{ marginBottom:16 }}>
          <label style={{ display:"block", fontSize:11, fontWeight:600, color:"var(--color-muted)", marginBottom:6, letterSpacing:".04em", textTransform:"uppercase" }}>Revision feedback (optional)</label>
          <textarea
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
            placeholder="Leave blank to approve as-is, or describe what needs changing…"
            rows={3}
            style={{ width:"100%", resize:"none", padding:"10px 12px", borderRadius:8, border:"1px solid var(--color-divider)", background:"var(--color-bg)", color:"var(--color-text)", fontSize:13, fontFamily:"var(--font-sans)", outline:"none", boxSizing:"border-box" }}
          />
        </div>

        {error && <div style={{ marginBottom:12, padding:"8px 12px", borderRadius:8, background:"rgba(244,63,94,.08)", border:"1px solid rgba(244,63,94,.2)", color:"var(--color-error)", fontSize:12 }}>{error}</div>}

        <div style={{ display:"flex", gap:10 }}>
          <button onClick={revise} disabled={loading}
            style={{ flex:1, padding:"10px 0", borderRadius:8, border:"1px solid var(--color-divider)", background:"transparent", color:"var(--color-text)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)" }}>
            Request Revision
          </button>
          <button onClick={approve} disabled={loading}
            style={{ flex:1, padding:"10px 0", borderRadius:8, border:"none", background:"var(--color-accent)", color:"#fff", fontSize:13, fontWeight:600, cursor:"pointer", fontFamily:"var(--font-sans)", display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
            {loading && <span style={{ width:12, height:12, borderRadius:"50%", border:"2px solid rgba(255,255,255,.3)", borderTopColor:"#fff", animation:"spin .8s linear infinite", display:"inline-block" }} />}
            ✓ Approve
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Requirement change panel ──────────────────────────────────────────────────
type ImpactAnalysis = {
  change_id: string
  description: string
  affected_stages: string[]
  safe_stages: string[]
  affected_files: string[]
  sprints_to_replan: number[]
  estimated_rerun_time: string
  explanation: string
  can_preserve: string[]
}

function RequirementChangePanel({ projectId }: { projectId: string }) {
  const [description, setDescription] = useState("")
  const [loading, setLoading] = useState(false)
  const [impact, setImpact] = useState<ImpactAnalysis | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<ImpactAnalysis[]>([])

  // Load existing changes on mount
  useEffect(() => {
    api.listChanges(projectId).then(res => {
      setHistory((res.changes ?? []) as ImpactAnalysis[])
    }).catch(() => {})
  }, [projectId])

  async function analyze() {
    if (!description.trim()) return
    setError(null)
    setLoading(true)
    setImpact(null)
    setDone(null)
    try {
      const res = await api.submitChange(projectId, description.trim())
      setImpact(res as unknown as ImpactAnalysis)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed")
    } finally {
      setLoading(false)
    }
  }

  async function confirm() {
    if (!impact) return
    setConfirming(true)
    try {
      await api.confirmChange(projectId, impact.change_id, true, "")
      setDone("confirmed")
      setHistory(h => [impact!, ...h])
      setImpact(null)
      setDescription("")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Confirm failed")
    } finally { setConfirming(false) }
  }

  async function cancel() {
    if (!impact) return
    try {
      await api.cancelChange(projectId, impact.change_id)
    } catch { /* ignore */ }
    setImpact(null)
    setDone("cancelled")
  }

  const pill = (text: string, color: string) => (
    <span style={{ fontSize:11, padding:"2px 8px", borderRadius:100, background:`rgba(${color},.12)`, color:`rgb(${color})`, border:`1px solid rgba(${color},.25)` }}>
      {text}
    </span>
  )

  return (
    <div style={{ flex:1, overflowY:"auto", padding:4, display:"flex", flexDirection:"column", gap:16 }}>

      {/* Input card */}
      <div style={{ background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:16, display:"flex", flexDirection:"column", gap:12 }}>
        <div className="ws-section-title">Request a Requirement Change</div>
        <p style={{ fontSize:12, color:"var(--color-muted)", margin:0 }}>
          Describe what you want to add, remove, or modify. The system will analyze which stages need to re-run and which can be preserved.
        </p>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="e.g. Add a dark mode toggle to the settings page…"
          rows={3}
          style={{ width:"100%", padding:"8px 10px", fontSize:13, background:"var(--color-bg)", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", color:"var(--color-text)", fontFamily:"var(--font-sans)", resize:"vertical", outline:"none", boxSizing:"border-box" }}
        />
        {error && (
          <div style={{ padding:"8px 12px", borderRadius:8, background:"rgba(244,63,94,.08)", border:"1px solid rgba(244,63,94,.2)", color:"var(--color-error)", fontSize:12 }}>{error}</div>
        )}
        {done === "confirmed" && (
          <div style={{ padding:"8px 12px", borderRadius:8, background:"rgba(16,185,129,.08)", border:"1px solid rgba(16,185,129,.2)", color:"var(--color-success)", fontSize:12 }}>
            ✓ Change confirmed — pipeline will re-run affected stages.
          </div>
        )}
        {done === "cancelled" && (
          <div style={{ padding:"8px 12px", borderRadius:8, background:"rgba(233,233,237,.05)", border:"1px solid var(--color-divider)", color:"var(--color-muted)", fontSize:12 }}>
            Change cancelled.
          </div>
        )}
        <button
          onClick={analyze}
          disabled={loading || !description.trim()}
          style={{ alignSelf:"flex-start", padding:"8px 18px", border:"none", borderRadius:"var(--radius-md)", background:"var(--color-accent)", color:"#fff", fontSize:13, fontWeight:600, cursor:loading||!description.trim()?"not-allowed":"pointer", fontFamily:"var(--font-sans)", opacity:loading||!description.trim()?.6:1, display:"flex", alignItems:"center", gap:8 }}>
          {loading && <span style={{ width:12, height:12, borderRadius:"50%", border:"2px solid rgba(255,255,255,.3)", borderTopColor:"#fff", animation:"spin .8s linear infinite", display:"inline-block" }} />}
          Analyze Impact
        </button>
      </div>

      {/* Impact analysis result */}
      {impact && (
        <div style={{ background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:16, display:"flex", flexDirection:"column", gap:14 }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <div className="ws-section-title" style={{ flex:1 }}>Impact Analysis</div>
            <span style={{ fontSize:11, color:"var(--color-muted)" }}>{impact.estimated_rerun_time}</span>
          </div>

          <p style={{ fontSize:13, color:"var(--color-text)", margin:0, lineHeight:1.55 }}>{impact.explanation}</p>

          {impact.affected_stages.length > 0 && (
            <div>
              <div style={{ fontSize:11, fontWeight:600, color:"var(--color-warning)", textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 }}>
                Must Re-run ({impact.affected_stages.length} stages)
              </div>
              <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                {impact.affected_stages.map(s => pill(s.replace(/_/g," "), "245,158,11"))}
              </div>
            </div>
          )}

          {impact.can_preserve.length > 0 && (
            <div>
              <div style={{ fontSize:11, fontWeight:600, color:"var(--color-success)", textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 }}>
                Preserved ({impact.can_preserve.length} artifacts)
              </div>
              <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                {impact.can_preserve.map(s => pill(s.replace(/_/g," "), "16,185,129"))}
              </div>
            </div>
          )}

          {impact.affected_files.length > 0 && (
            <div>
              <div style={{ fontSize:11, fontWeight:600, color:"var(--color-muted)", textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 }}>
                Files to Regenerate ({impact.affected_files.length})
              </div>
              <div style={{ maxHeight:120, overflowY:"auto", display:"flex", flexDirection:"column", gap:3 }}>
                {impact.affected_files.map((f, i) => (
                  <span key={i} style={{ fontSize:11, fontFamily:"var(--font-mono, monospace)", color:"var(--color-muted)", padding:"1px 6px", background:"rgba(233,233,237,.04)", borderRadius:4 }}>{f}</span>
                ))}
              </div>
            </div>
          )}

          <div style={{ display:"flex", gap:10, marginTop:4 }}>
            <button onClick={cancel} disabled={confirming}
              style={{ flex:1, padding:"9px 0", borderRadius:8, border:"1px solid var(--color-divider)", background:"transparent", color:"var(--color-text)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)" }}>
              Cancel
            </button>
            <button onClick={confirm} disabled={confirming}
              style={{ flex:2, padding:"9px 0", borderRadius:8, border:"none", background:"var(--color-accent)", color:"#fff", fontSize:13, fontWeight:600, cursor:confirming?"not-allowed":"pointer", fontFamily:"var(--font-sans)", display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
              {confirming && <span style={{ width:12, height:12, borderRadius:"50%", border:"2px solid rgba(255,255,255,.3)", borderTopColor:"#fff", animation:"spin .8s linear infinite", display:"inline-block" }} />}
              ✓ Confirm Change
            </button>
          </div>
        </div>
      )}

      {/* Change history */}
      {history.length > 0 && (
        <div style={{ background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)", padding:16, display:"flex", flexDirection:"column", gap:10 }}>
          <div className="ws-section-title">Change History</div>
          {history.map((c, i) => (
            <div key={i} style={{ padding:"10px 12px", borderRadius:8, border:"1px solid var(--color-divider)", display:"flex", flexDirection:"column", gap:6 }}>
              <div style={{ fontSize:12, color:"var(--color-text)", lineHeight:1.4 }}>{c.description}</div>
              <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
                <span style={{ fontSize:11, color:"var(--color-warning)" }}>~{c.affected_stages?.length ?? 0} stages affected</span>
                {c.estimated_rerun_time && <span style={{ fontSize:11, color:"var(--color-muted)" }}>• {c.estimated_rerun_time}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────
function EmptyState({ onStart, starting }: { onStart: () => void; starting: boolean }) {
  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:20, padding:40, textAlign:"center", background:"var(--color-surface)", borderRadius:"var(--radius-md)", boxShadow:"0 0 0 1px rgba(233,233,237,.08)" }}>
      <div style={{ width:60, height:60, borderRadius:16, background:"rgba(233,233,237,.05)", border:"1px solid var(--color-divider)", display:"grid", placeItems:"center" }}>
        <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="rgba(233,233,237,.2)" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      <div>
        <p style={{ fontWeight:600, fontSize:15, margin:"0 0 6px" }}>Ready to build</p>
        <p style={{ color:"var(--color-muted)", fontSize:13, margin:0, maxWidth:280 }}>
          Start the pipeline to begin the autonomous development process. AI agents will handle everything from planning to code generation.
        </p>
      </div>
      <button onClick={onStart} disabled={starting}
        style={{ display:"flex", alignItems:"center", gap:8, padding:"11px 28px", background:"var(--color-accent)", border:"none", borderRadius:"var(--radius-md)", color:"#fff", fontSize:14, fontWeight:600, cursor:starting?"not-allowed":"pointer", fontFamily:"var(--font-sans)", opacity:starting?.6:1 }}>
        {starting
          ? <span style={{ width:14, height:14, borderRadius:"50%", border:"2px solid rgba(255,255,255,.3)", borderTopColor:"#fff", animation:"spin .8s linear infinite", display:"inline-block" }} />
          : <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>}
        Start Build Pipeline
      </button>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export function WorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const activeTab = searchParams.get("tab") ?? "activity"

  const [project, setProject]   = useState<ProjectDetail | null>(null)
  const [cost, setCost]         = useState<CostSummary | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [designOpen, setDesignOpen] = useState(false)
  const [contextWarning, setContextWarning] = useState<{ pct: number; used: number; limit: number } | null>(null)
  const [gateOpen, setGateOpen] = useState<string | null>(null)
  // Track whether the user explicitly dismissed the modal without completing review.
  // Prevents the modal from re-opening on every WebSocket state update while the
  // pipeline is still in design_review state.
  const designDismissedRef = useRef(false)

  const { pipeline, liveLogs, connected, refresh } = usePipeline(projectId ?? null, setContextWarning)
  const logEvents = useLogs(projectId ?? null)

  const loadProject = useCallback(() => {
    if (!projectId) return
    api.getProject(projectId).then(setProject).catch(() => {})
    api.getCost(projectId).then(setCost).catch(() => {})
  }, [projectId])

  useEffect(() => { loadProject() }, [loadProject])

  useEffect(() => {
    const s = pipeline.state.toLowerCase()
    if (s.includes("design_review") || s === "design_ready") {
      // Only auto-open if the user hasn't explicitly dismissed this review session
      if (!designDismissedRef.current) {
        setDesignOpen(true)
      }
    } else if (s === "architecture_review_pending") {
      setGateOpen("architecture")
    } else if (s === "sprint_plan_review_pending") {
      setGateOpen("sprint_plan")
    } else {
      // Pipeline moved past design_review — reset dismissed flag for the next review
      designDismissedRef.current = false
      setGateOpen(null)
    }
  }, [pipeline.state])

  async function handleStart() {
    if (!projectId || !project) return
    setStarting(true)
    try {
      await api.startWorkflow(projectId, project.description || `Build ${project.name}`)
      await refresh()
    } finally { setStarting(false) }
  }

  async function handleStop() {
    if (!projectId) return
    setStopping(true)
    try { await api.stopWorkflow(projectId) } finally { setStopping(false) }
  }

  const s = pipeline.state.toLowerCase()
  const showQA     = s === "qa_pending"
  const notStarted = pipeline.status === "not_started" || pipeline.status === "stopped"

  // Sprint badge text
  const sprintBadge = pipeline.total_sprints > 0
    ? `Sprint ${pipeline.current_sprint} of ${pipeline.total_sprints}`
    : null

  // Format cost values
  const tokenStr = cost
    ? cost.total_tokens >= 1000 ? `${Math.round(cost.total_tokens / 1000)}K` : String(cost.total_tokens)
    : "—"
  const latencyStr = cost
    ? cost.total_latency_ms >= 60000
      ? `${Math.floor(cost.total_latency_ms / 60000)}m ${Math.round((cost.total_latency_ms % 60000) / 1000)}s`
      : `${Math.round(cost.total_latency_ms / 1000)}s`
    : "—"

  if (!project) {
    return (
      <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", color:"var(--color-muted)" }}>
        <span className="ic-running" style={{ marginRight:8 }} /> Loading…
      </div>
    )
  }

  return (
    <div style={{ display:"grid", gridTemplateColumns:"240px 1fr", gridTemplateRows:"56px 1fr", height:"100%", overflow:"hidden" }}>

      {/* ── Top nav (full width) ─────────────────────────────── */}
      <nav style={{ gridColumn:"1/3", borderBottom:"1px solid var(--color-divider)", display:"flex", alignItems:"center", gap:16, padding:"0 16px", flexShrink:0 }}>
        {/* Logo */}
        <div style={{ display:"flex", alignItems:"center", gap:8, fontWeight:500, fontSize:16 }}>
          <IcDiamond />
          AI DevOS
        </div>

        {/* Breadcrumb */}
        <div style={{ flex:1, display:"flex", alignItems:"center", gap:6, fontSize:13, paddingLeft:16, opacity:.65 }}>
          <span style={{ cursor:"pointer" }} onClick={() => navigate("/projects")}>Projects</span>
          <span style={{ opacity:.5 }}>/</span>
          <span style={{ opacity:1, fontWeight:500 }}>{project.name}</span>
        </div>

        {/* Right controls */}
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          {/* Live indicator */}
          <div style={{ display:"flex", alignItems:"center", gap:5, fontSize:11, padding:"3px 10px", borderRadius:100, border:"1px solid var(--color-divider)", color:connected?"var(--color-accent)":"var(--color-muted)" }}>
            <span style={{ width:5, height:5, borderRadius:"50%", background:connected?"var(--color-accent)":"rgba(233,233,237,.25)", display:"inline-block", animation:connected?"pulse-o 1.4s ease-in-out infinite":"none" }} />
            {connected ? "Live" : "Polling"}
          </div>

          {/* Sprint badge */}
          {sprintBadge && (
            <span style={{ fontSize:11, padding:"3px 10px", borderRadius:4, background:"rgba(145,132,217,.15)", color:"var(--color-accent)", border:"1px solid rgba(145,132,217,.25)" }}>
              {sprintBadge}
            </span>
          )}

          {/* Quick Build mode badge */}
          {project.mode === "quick" && (
            <span style={{ fontSize:11, padding:"3px 10px", borderRadius:4, background:"rgba(16,185,129,.12)", color:"var(--color-success)", border:"1px solid rgba(16,185,129,.2)" }}>
              ⚡ Quick Build
            </span>
          )}

          {/* Action buttons */}
          {pipeline.status === "running" ? (
            <button onClick={handleStop} disabled={stopping}
              style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 14px", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", background:"transparent", color:"var(--color-text)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)" }}>
              {stopping ? <span className="ic-running" style={{ width:10, height:10 }} /> : <IcSquare />}
              Stop
            </button>
          ) : notStarted ? (
            <button onClick={handleStart} disabled={starting}
              style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 14px", border:"1px solid var(--color-accent)", borderRadius:"var(--radius-md)", background:"transparent", color:"var(--color-accent)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)" }}>
              {starting && <span className="ic-running" style={{ width:10, height:10, borderTopColor:"var(--color-accent)" }} />}
              ▶ Start Build
            </button>
          ) : pipeline.status === "paused" ? (
            <button onClick={async () => { await api.continueWorkflow(projectId!); await refresh() }}
              style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 14px", border:"1px solid var(--color-accent)", borderRadius:"var(--radius-md)", background:"transparent", color:"var(--color-accent)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)" }}>
              ▶ Continue
            </button>
          ) : null}

          {pipeline.requires_user_action && (
            <button
              onClick={() => {
                if (s === "qa_pending") {
                  alert("Please go to the Q&A tab to answer questions.")
                } else if (s.includes("design_review") || s === "design_ready") {
                  designDismissedRef.current = false
                  setDesignOpen(true)
                } else if (s === "architecture_review_pending") {
                  setGateOpen("architecture")
                } else if (s === "sprint_plan_review_pending") {
                  setGateOpen("sprint_plan")
                } else {
                  alert(`Pipeline is paused in state: ${pipeline.state}. Please check the server logs for errors.`)
                }
              }}
              style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 14px", border:"1px solid rgba(245,158,11,.3)", borderRadius:"var(--radius-md)", background:"rgba(245,158,11,.08)", color:"var(--color-warning)", fontSize:13, cursor:"pointer", fontFamily:"var(--font-sans)", animation:"pulse-o 2s ease-in-out infinite" }}>
              {s === "qa_pending" ? "⚡ Answer Q&A" :
               (s.includes("design_review") || s === "design_ready") ? "⚡ Review Design" :
               s === "architecture_review_pending" ? "⚡ Review Architecture" :
               s === "sprint_plan_review_pending" ? "⚡ Review Sprint Plan" :
               "⚡ Action Needed"}
            </button>
          )}

          {/* Download */}
          <a href={api.downloadUrl(projectId!)} target="_blank" rel="noreferrer"
            style={{ display:"flex", alignItems:"center", gap:5, padding:"6px 14px", border:"1px solid var(--color-divider)", borderRadius:"var(--radius-md)", color:"var(--color-muted)", fontSize:13, textDecoration:"none" }}>
            ⬇ Download
          </a>
        </div>
      </nav>

      {/* ── Left sidebar: pipeline stages ───────────────────── */}
      <StageSidebar
        completedStages={pipeline.stages_completed}
        currentStage={pipeline.current_stage}
        failedStage={pipeline.failed_stage}
      />

      {/* ── Main content ─────────────────────────────────────── */}
      <div style={{ display:"flex", flexDirection:"column", gap:12, padding:16, overflow:"hidden", minHeight:0 }}>

        {/* Stat cards row — always visible */}
        <div style={{ display:"flex", gap:10, flexShrink:0 }}>
          <StatCard label="API CALLS"  value={cost?.calls ?? "—"} />
          <StatCard label="TOKENS"     value={tokenStr} />
          <StatCard label="LATENCY"    value={latencyStr} />
          <StatCard label="PROGRESS"   value={`${pipeline.progress_percent ?? 0}%`} />
        </div>

        {/* Tab: activity (default) */}
        {activeTab === "activity" && (
          showQA ? (
            <QAPanel
              projectId={projectId!}
              onComplete={async () => { loadProject(); await refresh() }}
            />
          ) : notStarted ? (
            <EmptyState onStart={handleStart} starting={starting} />
          ) : (
            <div style={{ display:"grid", gridTemplateColumns:"1fr 340px", gap:12, flex:1, minHeight:0 }}>
              <LogPanel events={logEvents} liveLogs={liveLogs} currentStage={pipeline.current_stage} />
              <div style={{ display:"flex", flexDirection:"column", gap:12, minHeight:0, overflow:"hidden" }}>
                <FilesPanel projectId={projectId!} />
                <ChatPanel projectId={projectId!} />
              </div>
            </div>
          )
        )}

        {/* Tab: files */}
        {activeTab === "files" && (
          <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column" }}>
            <FilesPanel projectId={projectId!} />
          </div>
        )}

        {/* Tab: artifacts */}
        {activeTab === "artifacts" && (
          <ArtifactsPanel artifacts={project?.artifacts ?? []} />
        )}

        {/* Tab: metrics */}
        {activeTab === "metrics" && (
          <MetricsPanel cost={cost} pipeline={pipeline} />
        )}

        {/* Tab: chat */}
        {activeTab === "chat" && (
          <div style={{ flex:1, display:"flex", flexDirection:"column", minHeight:0 }}>
            <ChatPanel projectId={projectId!} />
          </div>
        )}

        {/* Tab: integrations */}
        {activeTab === "integrations" && (
          <div style={{ flex:1, display:"flex", flexDirection:"column", minHeight:0 }}>
            <IntegrationsPanel projectId={projectId!} />
          </div>
        )}

        {/* Tab: changes */}
        {activeTab === "changes" && (
          <div style={{ flex:1, display:"flex", flexDirection:"column", minHeight:0 }}>
            <RequirementChangePanel projectId={projectId!} />
          </div>
        )}
      </div>

      {/* Context window warning banner */}
      {contextWarning && (
        <div style={{ position:"fixed", bottom:16, right:16, zIndex:40, maxWidth:340, padding:"12px 16px", borderRadius:12, background:"rgba(245,158,11,.1)", border:"1px solid rgba(245,158,11,.3)", color:"var(--color-warning)", fontSize:12, display:"flex", alignItems:"center", gap:10, boxShadow:"0 8px 24px rgba(0,0,0,.3)", animation:"slide-up .2s ease-out" }}>
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round" style={{ flexShrink:0 }}><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z M12 9v4 M12 17h.01" /></svg>
          <span style={{ flex:1 }}>Context window {contextWarning.pct}% full ({Math.round(contextWarning.used/1000)}K / {Math.round(contextWarning.limit/1000)}K tokens)</span>
          <button onClick={() => setContextWarning(null)} style={{ background:"none", border:"none", cursor:"pointer", color:"var(--color-warning)", padding:0, fontSize:14, lineHeight:1 }}>✕</button>
        </div>
      )}

      {/* Architecture / Sprint plan gate modal */}
      {gateOpen && (
        <GateModal
          projectId={projectId!}
          gate={gateOpen}
          onDone={() => { setGateOpen(null); loadProject(); refresh() }}
        />
      )}

      {/* Design review modal */}
      {designOpen && (
        <DesignReviewModal
          projectId={projectId!}
          onClose={() => {
            // Mark as dismissed so WS events don't re-open it automatically
            designDismissedRef.current = true
            setDesignOpen(false)
          }}
          onActionCompleted={async () => {
            // Review completed — clear dismissed flag, pipeline will advance past design_review
            designDismissedRef.current = false
            setDesignOpen(false)
            loadProject()
            await refresh()
          }}
        />
      )}

      {/* Clarification panel (legacy overlay) — kept for cases where clarification_questions
          appear before the QA state machine has taken over (state === "clarifying" still). */}
      {pipeline.status === "paused" && pipeline.state === "clarifying" && pipeline.clarification_questions && pipeline.clarification_questions.length > 0 && (
        <ClarificationPanel
          projectId={projectId!}
          questions={pipeline.clarification_questions}
          onComplete={async () => {
            loadProject()
            await refresh()
          }}
        />
      )}
    </div>
  )
}

import {
  useState, useEffect, useRef, useCallback,
} from "react"
import { useParams, Link } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import {
  api, STAGES, STAGE_LABELS, type LogEvent,
  type ArtifactDetail, type ArtifactHistoryItem, type QASession,
  type GateInfo, type MemorySummary, type CostSummary, type ProjectFiles,
  type FileContent, type DesignReviewData,
} from "../lib/api"
import { usePipeline } from "../hooks/usePipeline"
import { useLogs } from "../hooks/useLogs"
import { addToast } from "../components/ui/Toast"

/* ──────────────────────────────────────────────────────── Types */
type TabId = "overview" | "pipeline" | "artifacts" | "files" | "logs" | "metrics" | "chat" | "changes"

/* ──────────────────────────────────────────────────────── Stage status helpers */
function getStageStatus(stage: string, ws: { stages_completed?: string[]; completed_stages?: string[]; failed_stage: string | null; current_stage: string | null; requires_user_action?: boolean } | null): "pending" | "running" | "complete" | "failed" | "blocked" {
  if (!ws) return "pending"
  const done = ws.completed_stages ?? ws.stages_completed ?? []
  if (done.includes(stage)) return "complete"
  if (ws.failed_stage === stage) return "failed"
  if (ws.current_stage === stage) {
    if (ws.requires_user_action) return "blocked"
    return "running"
  }
  return "pending"
}

function StageIndicator({ status, num }: { status: string; num: number }) {
  const cls = {
    complete: "si-complete", running: "si-running",
    failed: "si-failed", blocked: "si-blocked", pending: "",
  }[status] ?? ""

  return (
    <div className={`stage-indicator ${cls}`}>
      {status === "complete" ? "✓" : status === "failed" ? "✗" : num}
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Gate modal */
function GateModal({ projectId, gate, onDone }: { projectId: string; gate: GateInfo; onDone: () => void }) {
  const [feedback, setFeedback] = useState("")
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<"artifact" | "feedback">("artifact")

  const approve = async () => {
    setLoading(true)
    try {
      await api.approveGate(projectId, gate.gate)
      onDone()
    } catch { setLoading(false) }
  }

  const revise = async () => {
    if (!feedback.trim()) return
    setLoading(true)
    try {
      await api.reviseGate(projectId, gate.gate, feedback)
      onDone()
    } catch { setLoading(false) }
  }

  const artifact = gate.artifact ? JSON.stringify(gate.artifact, null, 2) : null

  return (
    <div className="modal-overlay">
      <div className="modal modal-lg">
        <div className="modal-header">
          <div>
            <div className="modal-title">Review Required — {gate.gate.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{gate.instructions}</div>
          </div>
        </div>

        <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
          {["artifact", "feedback"].map(v => (
            <button key={v} className={`tab ${view === v ? "active" : ""}`} onClick={() => setView(v as any)}>
              {v === "artifact" ? "Artifact" : "Request Revision"}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {view === "artifact" && artifact && (
            <pre className="artifact-content" style={{ maxHeight: 400, fontSize: 12 }}>{artifact}</pre>
          )}
          {view === "artifact" && !artifact && (
            <div className="empty-state" style={{ padding: 32 }}>No artifact data available.</div>
          )}
          {view === "feedback" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
                Describe the changes you want before proceeding.
              </p>
              <textarea
                className="input"
                value={feedback}
                onChange={e => setFeedback(e.target.value)}
                rows={6}
                placeholder="e.g. Add error handling to the authentication module, split the user service into smaller responsibilities…"
              />
            </div>
          )}
        </div>

        <div className="modal-footer">
          {view === "feedback" ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              className="btn"
              onClick={revise}
              disabled={loading || !feedback.trim()}
              style={{
                background: "rgba(244,63,94,0.15)",
                border: "1px solid rgba(244,63,94,0.3)",
                color: "#F43F5E",
                opacity: (loading || !feedback.trim()) ? 0.5 : 1,
              }}
            >
              {loading && <div className="spinner spinner-sm" />}
              ✗ Submit Revision
            </motion.button>
          ) : null}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn"
            onClick={approve}
            disabled={loading}
            style={{
              background: "linear-gradient(135deg, #10B981, #06B6D4)",
              color: "#fff",
              boxShadow: "0 4px 14px rgba(16,185,129,0.3)",
              border: "none",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
            ✓ Approve & Continue
          </motion.button>
        </div>
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Design Review Modal */
function DesignReviewModal({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const [data, setData] = useState<DesignReviewData | null>(null)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [feedback, setFeedback] = useState("")
  const [view, setView] = useState<"spec" | "preview" | "feedback">("spec")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getDesignReview(projectId).then(setData).catch(() => {})
    api.getDesignPreview(projectId).then(r => setPreviewHtml(r.html)).catch(() => {})
  }, [projectId])

  const submit = async (approved: boolean) => {
    setLoading(true)
    try {
      await api.postDesignReview(projectId, approved, feedback || undefined)
      onDone()
    } catch { setLoading(false) }
  }

  return (
    <div className="modal-overlay">
      <div className="modal modal-xl">
        <div className="modal-header">
          <div>
            <div className="modal-title">Design Review</div>
            {data && <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>Iteration {data.review_iteration}</div>}
          </div>
        </div>

        <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
          {(["spec", "preview", "feedback"] as const).map(v => (
            <button key={v} className={`tab ${view === v ? "active" : ""}`} onClick={() => setView(v)}>
              {v === "spec" ? "Design Spec" : v === "preview" ? "Visual Preview" : "Revision Notes"}
            </button>
          ))}
        </div>

        <div className="modal-body" style={{ minHeight: 400 }}>
          {view === "spec" && data && (
            <pre className="artifact-content" style={{ maxHeight: 500 }}>
              {JSON.stringify(data.design, null, 2)}
            </pre>
          )}
          {view === "preview" && (
            previewHtml
              ? <iframe srcDoc={previewHtml} style={{ width: "100%", height: 480, border: "none", borderRadius: "var(--radius-md)", background: "#fff" }} sandbox="allow-scripts" title="Design preview" />
              : <div className="empty-state">No preview available</div>
          )}
          {view === "feedback" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Optionally describe changes you'd like before approving.</p>
              <textarea className="input" rows={6} value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Describe design changes…" />
            </div>
          )}
        </div>

        <div className="modal-footer">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn"
            onClick={() => submit(false)}
            disabled={loading}
            style={{
              background: "rgba(244,63,94,0.12)",
              border: "1px solid rgba(244,63,94,0.25)",
              color: "#F43F5E",
              opacity: loading ? 0.5 : 1,
            }}
          >
            {loading && <div className="spinner spinner-sm" />} ✗ Request Revision
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn"
            onClick={() => submit(true)}
            disabled={loading}
            style={{
              background: "linear-gradient(135deg, #10B981, #06B6D4)",
              color: "#fff",
              border: "none",
              boxShadow: "0 4px 14px rgba(16,185,129,0.3)",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />} ✓ Approve Design
          </motion.button>
        </div>
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── QA Panel */
function QAPanel({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const [session, setSession] = useState<QASession | null>(null)
  const [loading, setLoading] = useState(false)
  const [customAnswer, setCustomAnswer] = useState("")

  useEffect(() => {
    api.getQASession(projectId).then(setSession).catch(() => {})
  }, [projectId])

  const answer = async (ans: string) => {
    if (!session?.current_question) return
    setLoading(true)
    try {
      const r = await api.answerQA(projectId, session.current_question.index, ans)
      if (r.is_complete) {
        await api.completeQA(projectId)
        onDone()
      } else {
        const fresh = await api.getQASession(projectId)
        setSession(fresh)
        setCustomAnswer("")
      }
    } catch { } finally { setLoading(false) }
  }

  const skip = async () => {
    if (!session?.current_question) return
    setLoading(true)
    try {
      const r = await api.skipQA(projectId, session.current_question.index)
      if (r.is_complete) {
        await api.completeQA(projectId)
        onDone()
      } else {
        const fresh = await api.getQASession(projectId)
        setSession(fresh)
      }
    } catch { } finally { setLoading(false) }
  }

  if (!session) return <div style={{ display: "flex", justifyContent: "center", padding: 32 }}><div className="spinner" /></div>
  if (session.is_complete) return <div className="empty-state">Q&amp;A complete.</div>

  const q = session.current_question
  if (!q) return <div className="empty-state">No questions pending.</div>

  const progress = session.total_questions > 0
    ? Math.round((session.answered / session.total_questions) * 100)
    : 0

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 600, margin: "0 auto", padding: 24 }}>
      {/* Progress */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>
          <span>Question {session.answered + 1} of {session.total_questions}</span>
          <span>{progress}%</span>
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
      </div>

      {/* Category + question */}
      <div>
        {q.category && (
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 8 }}>
            {q.category}
          </div>
        )}
        <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>{q.question}</div>
      </div>

      {/* Options */}
      {q.options && q.options.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {q.options.map(opt => (
            <button
              key={opt.value}
              className="btn btn-secondary"
              style={{ justifyContent: "flex-start", textAlign: "left", padding: "10px 14px", height: "auto" }}
              onClick={() => answer(opt.value)}
              disabled={loading}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* Custom answer */}
      {q.allows_custom && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {q.options && q.options.length > 0 && (
            <div style={{ fontSize: 12, color: "var(--text-dim)", textAlign: "center" }}>— or type your own —</div>
          )}
          <textarea
            className="input"
            rows={3}
            value={customAnswer}
            onChange={e => setCustomAnswer(e.target.value)}
            placeholder="Your answer…"
            disabled={loading}
          />
          <button
            className="btn btn-primary"
            disabled={!customAnswer.trim() || loading}
            onClick={() => answer(customAnswer)}
          >
            {loading && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
            Submit Answer
          </button>
        </div>
      )}

      {/* Skip */}
      {q.skippable && (
        <button className="btn btn-ghost btn-sm" onClick={skip} disabled={loading} style={{ alignSelf: "center" }}>
          Skip this question
        </button>
      )}
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Artifacts Tab */
function ArtifactsTab({ projectId, completedStages }: { projectId: string; completedStages: string[] }) {
  const [selectedStage, setSelectedStage] = useState<string | null>(completedStages[0] ?? null)
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null)
  const [history, setHistory] = useState<ArtifactHistoryItem[]>([])
  const [view, setView] = useState<"content" | "structured" | "history">("content")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (completedStages.length > 0 && !selectedStage) {
      setSelectedStage(completedStages[completedStages.length - 1])
    }
  }, [completedStages, selectedStage])

  useEffect(() => {
    if (!selectedStage) return
    setLoading(true)
    Promise.all([
      api.getArtifact(projectId, selectedStage).catch(() => null),
      api.getArtifactHistory(projectId, selectedStage).catch(() => []),
    ]).then(([a, h]) => {
      setArtifact(a)
      setHistory(h)
      setLoading(false)
    })
  }, [projectId, selectedStage])

  if (completedStages.length === 0) {
    return <div className="empty-state"><div style={{ opacity: 0.3, fontSize: 32 }}>○</div><div>No artifacts yet — run the pipeline to generate stage outputs.</div></div>
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Stage list */}
      <div style={{
        width: 160, flexShrink: 0, borderRight: "1px solid var(--border)",
        overflow: "auto", background: "var(--surface-1)",
      }}>
        <div style={{ padding: "10px 10px 6px", fontSize: 10, fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase", color: "var(--text-dim)" }}>Stages</div>
        {completedStages.map(s => (
          <div
            key={s}
            role="button"
            tabIndex={0}
            onClick={() => setSelectedStage(s)}
            onKeyDown={e => e.key === "Enter" && setSelectedStage(s)}
            style={{
              padding: "7px 12px",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 500,
              color: selectedStage === s ? "var(--accent-hi)" : "var(--text-muted)",
              background: selectedStage === s ? "var(--accent-lo)" : "transparent",
              borderLeft: `2px solid ${selectedStage === s ? "var(--accent)" : "transparent"}`,
              transition: "all 100ms",
            }}
          >
            {STAGE_LABELS[s as keyof typeof STAGE_LABELS] ?? s}
          </div>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {selectedStage && (
          <>
            <div className="tabs" style={{ padding: "0 16px" }}>
              {(["content", "structured", "history"] as const).map(v => (
                <button key={v} className={`tab ${view === v ? "active" : ""}`} onClick={() => setView(v)}>
                  {v.charAt(0).toUpperCase() + v.slice(1)}
                  {v === "history" && history.length > 0 && (
                    <span className="badge badge-neutral" style={{ marginLeft: 4, fontSize: 10 }}>{history.length}</span>
                  )}
                </button>
              ))}
            </div>
            <div style={{ flex: 1, overflow: "auto" }}>
              {loading && <div style={{ display: "flex", justifyContent: "center", padding: 32 }}><div className="spinner" /></div>}

              {!loading && view === "content" && (
                <ArtifactCodeBlock content={artifact?.content ?? "No content"} />
              )}

              {!loading && view === "structured" && (
                <ArtifactCodeBlock content={artifact?.structured ? JSON.stringify(artifact.structured, null, 2) : "No structured data"} />
              )}

              {!loading && view === "history" && (
                <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
                  {history.length === 0 && <div className="empty-state">No history</div>}
                  {history.map((h, i) => (
                    <div key={i} className="surface" style={{ padding: "12px 14px" }}>
                      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>Attempt {h.attempt}</span>
                        {h.approved
                          ? <span className="badge badge-success">Approved</span>
                          : <span className="badge badge-neutral">Revision</span>}
                      </div>
                      <pre style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>{h.content?.slice(0, 500)}{h.content?.length > 500 ? "…" : ""}</pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Files Tab */
function FilesTab({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ProjectFiles | null>(null)
  const [selected, setSelected] = useState<{ area: string; path: string } | null>(null)
  const [content, setContent] = useState<FileContent | null>(null)
  const [loading, setLoading] = useState(false)
  const [treeLoading, setTreeLoading] = useState(true)

  useEffect(() => {
    api.getFiles(projectId)
      .then(f => { setFiles(f); setTreeLoading(false) })
      .catch(() => setTreeLoading(false))
  }, [projectId])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    api.getFileContent(projectId, selected.area, selected.path)
      .then(c => { setContent(c); setLoading(false) })
      .catch(() => setLoading(false))
  }, [projectId, selected])

  const allFiles = [
    ...(files?.backend ?? []).map(p => ({ area: "backend", path: p })),
    ...(files?.frontend ?? []).map(p => ({ area: "frontend", path: p })),
  ]

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* File tree */}
      <div style={{ width: 220, flexShrink: 0, borderRight: "1px solid var(--border)", overflow: "auto", background: "var(--surface-1)" }}>
        {treeLoading && <div style={{ padding: 16, display: "flex", justifyContent: "center" }}><div className="spinner spinner-sm" /></div>}
        {!treeLoading && allFiles.length === 0 && (
          <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>No files generated yet.</div>
        )}
        {(["backend", "frontend"] as const).map(area => {
          const areaFiles = area === "backend" ? (files?.backend ?? []) : (files?.frontend ?? [])
          if (areaFiles.length === 0) return null
          return (
            <div key={area}>
              <div style={{ padding: "8px 12px 4px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--text-dim)" }}>
                {area}
              </div>
              {areaFiles.map(p => (
                <div
                  key={p}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelected({ area, path: p })}
                  onKeyDown={e => e.key === "Enter" && setSelected({ area, path: p })}
                  style={{
                    padding: "5px 12px",
                    cursor: "pointer",
                    fontSize: 12,
                    fontFamily: "monospace",
                    color: selected?.path === p && selected?.area === area ? "var(--accent-hi)" : "var(--text-muted)",
                    background: selected?.path === p && selected?.area === area ? "var(--accent-lo)" : "transparent",
                    borderLeft: `2px solid ${selected?.path === p && selected?.area === area ? "var(--accent)" : "transparent"}`,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={p}
                >
                  {p.split("/").pop()}
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* File content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {selected && (
          <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border)", fontSize: 12, fontFamily: "monospace", color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
            <span>{selected.area}/{selected.path}</span>
            <a href={`/api/projects/${projectId}/files/${selected.area}/${selected.path}`} target="_blank" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}>
              Raw ↗
            </a>
          </div>
        )}
        {loading && <div style={{ display: "flex", justifyContent: "center", padding: 32 }}><div className="spinner" /></div>}
        {!loading && content && (
          <pre className="artifact-content" style={{ flex: 1, margin: 0, borderRadius: 0 }}>{content.content}</pre>
        )}
        {!selected && !loading && (
          <div className="empty-state">Select a file to view its contents</div>
        )}
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Metrics Tab */
function MetricsTab({ projectId }: { projectId: string }) {
  const [cost, setCost] = useState<CostSummary | null>(null)
  const [memory, setMemory] = useState<MemorySummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getCost(projectId).catch(() => null),
      api.getMemory(projectId).catch(() => null),
    ]).then(([c, m]) => { setCost(c); setMemory(m); setLoading(false) })
  }, [projectId])

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><div className="spinner" /></div>

  return (
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 24, overflow: "auto" }}>
      {/* Cost */}
      {cost && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Token Usage</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
            {[
              { label: "LLM Calls", value: cost.calls.toLocaleString() },
              { label: "Prompt Tokens", value: cost.prompt_tokens.toLocaleString() },
              { label: "Completion Tokens", value: cost.completion_tokens.toLocaleString() },
              { label: "Total Tokens", value: cost.total_tokens.toLocaleString() },
              { label: "Total Latency", value: `${(cost.total_latency_ms / 1000).toFixed(1)}s` },
            ].map(item => (
              <div key={item.label} className="surface-2" style={{ padding: "12px 14px" }}>
                <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 500, marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "monospace", color: "var(--text)" }}>{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Memory */}
      {memory && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Memory & Learning</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10, marginBottom: 16 }}>
            {[
              { label: "Lessons", value: memory.lesson_count },
              { label: "Trajectories", value: memory.trajectory_count },
              { label: "Knowledge Records", value: memory.knowledge_entry_count },
            ].map(item => (
              <div key={item.label} className="surface-2" style={{ padding: "12px 14px" }}>
                <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 500, marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 18, fontWeight: 600, fontFamily: "monospace", color: "var(--text)" }}>{item.value}</div>
              </div>
            ))}
          </div>
          {memory.records.length > 0 && (
            <table className="data-table">
              <thead>
                <tr><th>Key</th><th>Preview</th><th>Stored At</th></tr>
              </thead>
              <tbody>
                {memory.records.slice(0, 20).map((r, i) => (
                  <tr key={i}>
                    <td className="td-primary" style={{ fontFamily: "monospace", fontSize: 11 }}>{r.key}</td>
                    <td style={{ maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12 }}>{r.value_preview}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 11, whiteSpace: "nowrap" }}>{new Date(r.stored_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Chat Tab */
function ChatTab({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; text: string }[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView()
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || sending) return
    setInput("")
    setMessages(m => [...m, { role: "user", text: msg }])
    setSending(true)
    try {
      const r = await api.sendChat(projectId, msg)
      setMessages(m => [...m, { role: "assistant", text: r.reply }])
    } catch (err: any) {
      setMessages(m => [...m, { role: "assistant", text: `Error: ${err.message}` }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
        {messages.length === 0 && (
          <div className="empty-state" style={{ margin: "auto 0" }}>
            <div style={{ opacity: 0.3, fontSize: 32 }}>💬</div>
            <div>Ask the AI about this project — architecture, decisions, next steps.</div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "80%",
            padding: "9px 13px",
            borderRadius: "var(--radius-lg)",
            fontSize: 13,
            lineHeight: 1.5,
            background: m.role === "user" ? "var(--accent)" : "var(--surface-2)",
            color: m.role === "user" ? "#fff" : "var(--text)",
            border: m.role === "assistant" ? "1px solid var(--border)" : "none",
          }}>
            {m.text}
          </div>
        ))}
        {sending && (
          <div style={{ alignSelf: "flex-start", padding: "9px 13px", borderRadius: "var(--radius-lg)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <div className="spinner spinner-sm" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)", display: "flex", gap: 8 }}>
        <input
          className="input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Ask about this project…"
          disabled={sending}
        />
        <button className="btn btn-primary" onClick={send} disabled={!input.trim() || sending}>
          {sending ? <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} /> : "Send"}
        </button>
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Changes Tab */
function ChangesTab({ projectId }: { projectId: string }) {
  const [description, setDescription] = useState("")
  const [changes, setChanges] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.listChanges(projectId)
      .then(r => { setChanges(r.changes ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [projectId])

  const submit = async () => {
    if (!description.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.submitChange(projectId, description.trim())
      setDescription("")
      const r = await api.listChanges(projectId)
      setChanges(r.changes ?? [])
    } catch (err: any) {
      setError(err.message)
    } finally { setSubmitting(false) }
  }

  return (
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 24, overflow: "auto", height: "100%" }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 10 }}>Request Requirement Change</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <textarea
            className="input"
            rows={4}
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Describe the change you need — the system will analyze impact before proceeding…"
          />
          {error && <div className="error-banner"><span>⚠</span> {error}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button className="btn btn-primary" onClick={submit} disabled={!description.trim() || submitting}>
              {submitting && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
              Submit Change Request
            </button>
          </div>
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Change History</div>
        {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><div className="spinner" /></div>}
        {!loading && changes.length === 0 && <div className="empty-state" style={{ padding: 24 }}>No changes requested yet.</div>}
        {changes.map((c, i) => (
          <div key={i} className="surface" style={{ padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span className={`badge ${c.status === "confirmed" ? "badge-success" : c.status === "cancelled" ? "badge-neutral" : "badge-warning"}`}>
                {c.status ?? "pending"}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-dim)", fontFamily: "monospace" }}>{c.change_id ?? `#${i + 1}`}</span>
            </div>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>{c.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Pipeline Tab */
function PipelineTab({ status }: { status: any }) {
  const currentIdx = status?.current_stage ? STAGES.indexOf(status.current_stage as any) : -1

  return (
    <div style={{ padding: 20, overflow: "auto" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, maxWidth: 640 }}>
        {STAGES.map((stage, i) => {
          const st = getStageStatus(stage, status)
          return (
            <div key={stage} style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 14,
              padding: "10px 14px",
              borderRadius: "var(--radius-md)",
              background: st === "running" ? "var(--accent-lo)" : st === "blocked" ? "var(--warning-lo)" : "transparent",
              border: `1px solid ${st === "running" ? "var(--accent-border)" : st === "blocked" ? "rgba(245,158,11,0.2)" : "transparent"}`,
              transition: "all 120ms",
            }}>
              <StageIndicator status={st} num={i + 1} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13,
                  fontWeight: 500,
                  color: st === "complete" ? "var(--text)"
                    : st === "running" ? "var(--accent-hi)"
                    : st === "failed" ? "var(--error)"
                    : st === "blocked" ? "var(--warning)"
                    : "var(--text-muted)",
                }}>
                  {STAGE_LABELS[stage]}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                  {st === "running" && "● Active"}
                  {st === "complete" && "✓ Complete"}
                  {st === "failed" && "✗ Failed"}
                  {st === "blocked" && "⊘ Awaiting review"}
                  {st === "pending" && i <= currentIdx ? "Queued" : st === "pending" ? "Pending" : ""}
                </div>
              </div>
              {st === "running" && (
                <div className="spinner spinner-sm" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Logs Tab */
function LogsTab({ logs }: { logs: LogEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView() }, [logs])

  return (
    <div className="log-stream">
      {logs.length === 0 && (
        <div className="empty-state">Logs will appear here as the pipeline runs.</div>
      )}
      {logs.map(log => (
        <div key={log.id} className="log-line">
          <span className="log-time">{new Date(log.created_at).toLocaleTimeString()}</span>
          <span className="log-stage">{log.stage}</span>
          <span className={`log-msg-${log.level}`}>{log.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Overview Tab */
function OverviewTab({ projectId, status, logs }: { projectId: string; status: any; logs: LogEvent[] }) {
  const progress = status?.progress_percent ?? 0
  const done = status?.completed_stages?.length ?? status?.stages_completed?.length ?? 0
  const total = status?.total_stages ?? STAGES.length
  const recentLogs = logs.slice(-8)

  return (
    <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 20, overflow: "auto" }}>
      {/* Progress */}
      <div className="surface" style={{ padding: "16px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10, alignItems: "center" }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Pipeline Progress</span>
          <span style={{ fontSize: 13, fontFamily: "monospace", color: "var(--text-muted)" }}>
            {done} / {total} stages
          </span>
        </div>
        <div className="progress-track" style={{ height: 6 }}>
          <div className={`progress-fill ${status?.status === "complete" ? "complete" : status?.status === "failed" ? "failed" : ""}`} style={{ width: `${progress}%` }} />
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>{Math.round(progress)}% complete</div>
      </div>

      {/* Status row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        {[
          { label: "Status", value: status?.status ?? "—", mono: false },
          { label: "Current Stage", value: status?.current_stage ? STAGE_LABELS[status.current_stage as keyof typeof STAGE_LABELS] ?? status.current_stage : "—", mono: false },
          { label: "Sprint", value: status?.current_sprint ? `${status.current_sprint} / ${status.total_sprints ?? "?"}` : "—", mono: true },
        ].map(s => (
          <div key={s.label} className="surface-2" style={{ padding: "12px 14px" }}>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", fontFamily: s.mono ? "monospace" : "inherit" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Recent logs */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 10 }}>Recent Activity</div>
        <div className="surface" style={{ padding: "8px 12px" }}>
          {recentLogs.length === 0
            ? <div style={{ fontSize: 12, color: "var(--text-dim)", padding: "8px 0" }}>No recent log events.</div>
            : recentLogs.map(log => (
              <div key={log.id} className="log-line" style={{ padding: "3px 0" }}>
                <span className="log-time">{new Date(log.created_at).toLocaleTimeString()}</span>
                <span className="log-stage">{log.stage}</span>
                <span className={`log-msg-${log.level}`}>{log.message}</span>
              </div>
            ))
          }
        </div>
      </div>

      {/* Download link (always show if available) */}
      <div>
        <a
          href={api.downloadUrl(projectId)}
          className="btn btn-secondary"
          style={{ width: "fit-content" }}
        >
          ↓ Download Project ZIP
        </a>
      </div>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Copy-enabled code block */
function ArtifactCodeBlock({ content }: { content: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <pre className="artifact-content" style={{ flex: 1, paddingTop: 36 }}>{content}</pre>
      <button
        onClick={handleCopy}
        style={{
          position: "absolute", top: 8, right: 8,
          padding: "3px 10px", borderRadius: 5,
          fontSize: 11, fontWeight: 600,
          background: copied ? "rgba(16,185,129,0.2)" : "rgba(255,255,255,0.07)",
          border: `1px solid ${copied ? "rgba(16,185,129,0.3)" : "rgba(255,255,255,0.1)"}`,
          color: copied ? "#10B981" : "#6b7280",
          cursor: "pointer", transition: "all 200ms", fontFamily: "inherit",
        }}
      >
        {copied ? "✓ Copied" : "Copy"}
      </button>
    </div>
  )
}

/* ──────────────────────────────────────────────────────── Main WorkspacePage */
export default function WorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [tab, setTab] = useState<TabId>("overview")
  const [gate, setGate] = useState<GateInfo | null>(null)
  const [showDesignReview, setShowDesignReview] = useState(false)
  const [showQA, setShowQA] = useState(false)

  const pid = projectId ?? ""
  const { pipeline: status, liveLogs } = usePipeline(pid)
  const logs = useLogs(pid)

  // Show toast notifications when files are written by the pipeline
  useEffect(() => {
    const lastLine = liveLogs[liveLogs.length - 1]
    if (lastLine && lastLine.startsWith("📄 ")) {
      const filename = lastLine.replace("📄 ", "").trim()
      addToast({ filename, type: "file" })
    }
  }, [liveLogs])

  // Check for gates when action is required
  useEffect(() => {
    if (!status?.requires_user_action || !pid) return

    // Check for QA state
    if (status.state === "qa_pending") {
      setShowQA(true)
      setGate(null)
      setShowDesignReview(false)
      return
    }

    // Check for design review
    if (status.state === "design_review_pending" || status.current_stage === "Designer") {
      if (status.requires_user_action) {
        setShowDesignReview(true)
        setGate(null)
        setShowQA(false)
        return
      }
    }

    // Fetch generic gate
    api.getCurrentGate(pid).then(g => {
      if (g) {
        setGate(g)
        setShowDesignReview(false)
        setShowQA(false)
      }
    }).catch(() => {})
  }, [status?.requires_user_action, status?.state, status?.current_stage, pid])

  const dismissGate = useCallback(async () => {
    setGate(null)
    setShowDesignReview(false)
    setShowQA(false)
  }, [])

  const handleStop = async () => {
    if (!pid) return
    try { await api.stopWorkflow(pid) } catch { }
  }

  const handleContinue = async () => {
    if (!pid) return
    try { await api.continueWorkflow(pid) } catch { }
  }

  const isFailed = status?.status === "failed"

  const handleRetry = async () => {
    if (!pid) return
    try {
      const failedStage = status?.failed_stage || status?.current_stage
      if (failedStage) {
        await api.runStage(pid, failedStage, "")
      } else {
        await api.continueWorkflow(pid)
      }
    } catch { }
  }

  const completedStages = status?.stages_completed ?? []
  const isRunning = status?.status === "running"
  const isPaused = status?.status === "paused" || status?.status === "stopped"

  const TABS: { id: TabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "pipeline", label: "Pipeline" },
    { id: "artifacts", label: `Artifacts${completedStages.length > 0 ? ` (${completedStages.length})` : ""}` },
    { id: "files", label: "Files" },
    { id: "logs", label: `Logs${logs.length > 0 ? ` (${logs.length})` : ""}` },
    { id: "metrics", label: "Metrics" },
    { id: "chat", label: "Chat" },
    { id: "changes", label: "Changes" },
  ]

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div className="page-header" style={{ gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <Link to="/projects" style={{ color: "var(--text-muted)", fontSize: 13, textDecoration: "none" }}>Projects</Link>
          <span style={{ color: "var(--text-dim)" }}>/</span>
          <span style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {pid.slice(0, 16)}…
          </span>
          {status && (
            <span className={`badge ${
              status.status === "running" ? "badge-accent" :
              status.status === "complete" ? "badge-success" :
              status.status === "failed" ? "badge-error" : "badge-neutral"
            }`}>
              {status.status === "running" && <div className="status-dot running" />}
              {status.status}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          {isRunning && (
            <button className="btn btn-secondary btn-sm" onClick={handleStop}>■ Stop</button>
          )}
          {isPaused && (
            <button className="btn btn-primary btn-sm" onClick={handleContinue}>▶ Continue</button>
          )}
          {isFailed && (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleRetry}
              style={{
                background: "linear-gradient(135deg, #7C3AED, #06B6D4)",
                color: "#fff",
                border: "none",
                boxShadow: "0 2px 10px rgba(124,58,237,0.3)",
              }}
            >
              ↺ Retry Stage
            </button>
          )}
          <a href={api.downloadUrl(pid)} className="btn btn-secondary btn-sm">↓ ZIP</a>
        </div>
      </div>

      {/* Action required banner */}
      <AnimatePresence>
      {status?.requires_user_action && (
        <motion.div
          className="action-banner"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div className="status-dot" style={{ background: "var(--accent)", animation: "pulse-status 1.2s ease-in-out infinite" }} />
            <span className="action-banner-text">Human review required</span>
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              if (showQA || status.state === "qa_pending") { setTab("overview") }
              else { setTab("overview") }
            }}
          >
            Review Now
          </button>
        </motion.div>
      )}
      </AnimatePresence>

      {/* Stat row */}
      {status && (
        <div className="stat-row">
          <div className="stat-cell">
            <div className="stat-label">Progress</div>
            <div className="stat-value">{Math.round(status.progress_percent ?? 0)}%</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Stage</div>
            <div className="stat-value" style={{ fontSize: 14 }}>
              {status.current_stage
                ? (STAGE_LABELS[status.current_stage as keyof typeof STAGE_LABELS] ?? status.current_stage)
                : "—"}
            </div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Completed</div>
            <div className="stat-value">{completedStages.length} <span style={{ fontSize: 12, color: "var(--text-muted)" }}>/ {status.total_stages}</span></div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Sprint</div>
            <div className="stat-value" style={{ fontSize: 14 }}>
              {status.current_sprint ? `${status.current_sprint}/${status.total_sprints ?? "?"}` : "—"}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        {TABS.map(t => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", position: "relative" }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: "easeInOut" }}
            style={{ position: "absolute", inset: 0, display: "flex", overflow: "hidden" }}
          >
            {tab === "overview" && (
              showQA ? <QAPanel projectId={pid} onDone={dismissGate} />
              : <OverviewTab projectId={pid} status={status} logs={logs} />
            )}
            {tab === "pipeline" && <PipelineTab status={status} />}
            {tab === "artifacts" && <ArtifactsTab projectId={pid} completedStages={completedStages} />}
            {tab === "files" && <FilesTab projectId={pid} />}
            {tab === "logs" && <LogsTab logs={logs} />}
            {tab === "metrics" && <MetricsTab projectId={pid} />}
            {tab === "chat" && <ChatTab projectId={pid} />}
            {tab === "changes" && <ChangesTab projectId={pid} />}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Gate Modal */}
      {gate && (
        <GateModal projectId={pid} gate={gate} onDone={dismissGate} />
      )}

      {/* Design Review Modal */}
      {showDesignReview && (
        <DesignReviewModal projectId={pid} onDone={dismissGate} />
      )}
    </div>
  )
}

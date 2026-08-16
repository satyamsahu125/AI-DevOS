import { useState, useEffect, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { api, type ProjectSummary, type ReadyStatus } from "../lib/api"

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  running:    { label: "Running",  color: "#06B6D4", bg: "rgba(6,182,212,0.12)",   border: "rgba(6,182,212,0.3)"   },
  complete:   { label: "Complete", color: "#10B981", bg: "rgba(16,185,129,0.12)",  border: "rgba(16,185,129,0.3)"  },
  failed:     { label: "Failed",   color: "#F43F5E", bg: "rgba(244,63,94,0.12)",   border: "rgba(244,63,94,0.3)"   },
  paused:     { label: "Paused",   color: "#F59E0B", bg: "rgba(245,158,11,0.12)",  border: "rgba(245,158,11,0.3)"  },
  stopped:    { label: "Stopped",  color: "#6B7280", bg: "rgba(107,114,128,0.10)", border: "rgba(107,114,128,0.25)" },
  not_started:{ label: "Idle",     color: "#6B7280", bg: "rgba(107,114,128,0.10)", border: "rgba(107,114,128,0.25)" },
}

function getStatusConfig(status: string) {
  return STATUS_CONFIG[status] ?? { label: status, color: "#6B7280", bg: "rgba(107,114,128,0.10)", border: "rgba(107,114,128,0.25)" }
}

function formatDate(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return "just now"
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return d.toLocaleDateString()
}

// ── Animation variants ────────────────────────────────────────────────────────
const containerVariant = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
}

const cardVariant = {
  hidden:  { opacity: 0, y: 20, scale: 0.97 },
  visible: {
    opacity: 1, y: 0, scale: 1,
    transition: { type: "spring" as const, stiffness: 260, damping: 22 },
  },
  exit: { opacity: 0, scale: 0.95, transition: { duration: 0.18 } },
}

const emptyVariant = {
  hidden:  { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45, ease: "easeOut" } },
}

// ── Aurora status badge ───────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const sc = getStatusConfig(status)
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 5,
      fontSize: 10,
      fontWeight: 600,
      padding: "3px 8px",
      borderRadius: 99,
      background: sc.bg,
      border: `1px solid ${sc.border}`,
      color: sc.color,
      letterSpacing: "0.03em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      {status === "running" && (
        <span style={{
          width: 5, height: 5, borderRadius: "50%",
          background: sc.color,
          display: "inline-block",
          animation: "pulse 1.4s ease-in-out infinite",
        }} />
      )}
      {sc.label}
    </span>
  )
}

function NewProjectModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [mode, setMode] = useState<"full" | "quick">("full")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !description.trim()) {
      setError("Name and description are required.")
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await api.createAndRunProject(name.trim(), description.trim(), mode)
      onCreate()
      navigate(`/projects/${result.id}`)
    } catch (err: any) {
      setError(err.message ?? "Failed to create project")
      setLoading(false)
    }
  }

  return (
    <motion.div
      className="modal-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        className="modal"
        initial={{ opacity: 0, y: 20, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 280, damping: 26 }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title">New Project</span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose}>
            <XIcon />
          </button>
        </div>

        <form onSubmit={handleCreate}>
          <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                Project Name
              </label>
              <input
                id="new-project-name"
                className="input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Task Manager API"
                maxLength={80}
                required
                autoFocus
              />
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                Description
              </label>
              <textarea
                id="new-project-description"
                className="input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe what you want to build. Be specific about features, tech stack, and constraints."
                rows={5}
                required
              />
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
                {description.length} characters — the more detail you provide, the better the output.
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 8 }}>
                Build Mode
              </label>
              <div style={{ display: "flex", gap: 8 }}>
                {(["full", "quick"] as const).map(m => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className="btn"
                    style={{
                      flex: 1,
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 3,
                      padding: "10px 12px",
                      height: "auto",
                      background: mode === m ? "var(--accent-lo)" : "var(--surface-2)",
                      border: `1px solid ${mode === m ? "var(--accent-border)" : "var(--border)"}`,
                      color: mode === m ? "var(--accent-hi)" : "var(--text-muted)",
                    }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 600 }}>
                      {m === "full" ? "Full Build" : "Quick Build"}
                    </span>
                    <span style={{ fontSize: 11, opacity: 0.7, fontWeight: 400, color: "var(--text-muted)" }}>
                      {m === "full" ? "All 20 stages — complete project" : "Condensed — faster output"}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {error && <div className="error-banner"><XCircleIcon /> {error}</div>}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button
              id="create-project-submit"
              type="submit"
              className="btn btn-primary"
              disabled={loading || !name.trim() || !description.trim()}
            >
              {loading && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
              {loading ? "Creating…" : "Create & Start"}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

function ProjectCard({ project, onDelete }: { project: ProjectSummary; onDelete: () => void }) {
  const navigate = useNavigate()
  const [deleting, setDeleting] = useState(false)
  const [hovered, setHovered] = useState(false)

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm(`Delete "${project.name}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await api.deleteProject(project.project_id)
      onDelete()
    } catch {
      setDeleting(false)
    }
  }

  return (
    <motion.div
      variants={cardVariant}
      whileHover={{ y: -3, transition: { type: "spring", stiffness: 320, damping: 24 } }}
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/projects/${project.project_id}`)}
      onKeyDown={e => e.key === "Enter" && navigate(`/projects/${project.project_id}`)}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      style={{
        background: hovered ? "var(--surface-2)" : "var(--surface-1)",
        border: `1px solid ${hovered ? "var(--border-md)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "16px 18px",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        position: "relative",
        transition: "background 120ms, border-color 120ms",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 14, fontWeight: 600, color: "var(--text)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {project.name}
          </div>
        </div>
        <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
          {project.mode === "quick" && (
            <span style={{
              fontSize: 9, fontWeight: 600, padding: "3px 6px",
              borderRadius: 4, textTransform: "uppercase", letterSpacing: "0.05em",
              background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)",
              color: "rgba(255,255,255,0.4)",
            }}>Quick</span>
          )}
          <StatusBadge status={project.status} />
        </div>
      </div>

      {/* Stage info */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
          {project.current_stage ? project.current_stage.replace(/([A-Z])/g, " $1").trim() : "—"}
        </span>
      </div>

      {/* Footer */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{formatDate(project.created_at)}</span>
        <motion.button
          className="btn btn-ghost btn-icon btn-sm"
          onClick={handleDelete}
          disabled={deleting}
          style={{ color: "var(--error)" }}
          initial={{ opacity: 0.4 }}
          animate={{ opacity: hovered ? 0.8 : 0.4 }}
          whileHover={{ opacity: 1 }}
          title="Delete project"
        >
          {deleting ? <div className="spinner spinner-sm" /> : <TrashIcon />}
        </motion.button>
      </div>
    </motion.div>
  )
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [health, setHealth] = useState<ReadyStatus | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ps, h] = await Promise.all([
        api.listProjects(),
        api.ready().catch(() => null),
      ])
      setProjects(ps)
      setHealth(h)
      setError(null)
    } catch (err: any) {
      setError(err.message ?? "Failed to load projects")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh while any project is running
  useEffect(() => {
    if (projects.some(p => p.status === "running")) {
      const id = setInterval(load, 5000)
      return () => clearInterval(id)
    }
  }, [projects, load])

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">Projects</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            {projects.length} project{projects.length !== 1 ? "s" : ""}
            {health && (
              <span style={{ marginLeft: 12 }}>
                <span className={`health-dot ${health.status === "ready" ? "ready" : "degraded"}`} style={{ display: "inline-block", marginRight: 4, verticalAlign: "middle" }} />
                {health.model}
              </span>
            )}
          </div>
        </div>
        <motion.button
          id="new-project-btn"
          className="btn btn-primary"
          onClick={() => setShowModal(true)}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          <PlusIcon />
          New Project
        </motion.button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
        {loading && projects.length === 0 && (
          <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
            <div className="spinner spinner-lg" />
          </div>
        )}

        {error && !loading && (
          <div className="error-banner" style={{ marginBottom: 16 }}>
            <XCircleIcon /> {error}
          </div>
        )}

        <AnimatePresence mode="wait">
          {!loading && projects.length === 0 && !error && (
            <motion.div
              key="empty"
              className="empty-state"
              variants={emptyVariant}
              initial="hidden"
              animate="visible"
              exit="hidden"
            >
              <motion.svg
                className="empty-icon"
                viewBox="0 0 40 40"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                animate={{ y: [0, -4, 0] }}
                transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
              >
                <path d="M5 11.5A3 3 0 018 8.5h8l3 4H32A3 3 0 0135 15.5v16a3 3 0 01-3 3H8a3 3 0 01-3-3v-20z"/>
              </motion.svg>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>No projects yet</div>
              <div style={{ fontSize: 13 }}>Create your first project to start building with AI agents.</div>
              <motion.button
                className="btn btn-primary"
                onClick={() => setShowModal(true)}
                style={{ marginTop: 8 }}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.97 }}
              >
                <PlusIcon /> New Project
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>

        {projects.length > 0 && (
          <motion.div
            variants={containerVariant}
            initial="hidden"
            animate="visible"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            <AnimatePresence>
              {projects.map(p => (
                <ProjectCard key={p.project_id} project={p} onDelete={load} />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>

      <AnimatePresence>
        {showModal && (
          <NewProjectModal
            onClose={() => setShowModal(false)}
            onCreate={() => { setShowModal(false); load() }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Icons ─────────────────────────────────────────────────── */
function PlusIcon() {
  return <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M8 2v12M2 8h12"/></svg>
}
function XIcon() {
  return <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>
}
function XCircleIcon() {
  return <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="8" cy="8" r="7"/><path d="M5 5l6 6M11 5l-6 6"/></svg>
}
function TrashIcon() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 10h8l1-10"/></svg>
}

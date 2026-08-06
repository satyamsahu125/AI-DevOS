import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, type ProjectSummary, type ReadyStatus, type LLMSettings, type ProviderInfo } from "../lib/api"
import { Spinner } from "../components/ui/Spinner"

// ── Status badge ──────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const color =
    status === "complete"   ? "bg-emerald-400" :
    status === "running"    ? "bg-indigo-400 animate-pulse" :
    status === "failed"     ? "bg-rose-400" :
    status === "paused"     ? "bg-amber-400" :
    status === "stopped"    ? "bg-zinc-500" :
                              "bg-zinc-600"
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
}

function statusLabel(s: string) {
  return s === "not_started" ? "Not started" :
         s.charAt(0).toUpperCase() + s.slice(1)
}

// ── New project modal ─────────────────────────────────────────────────────

function NewProjectModal({ onClose, onCreate }: { onClose: () => void; onCreate: (id: string) => void }) {
  const [name, setName] = useState("")
  const [desc, setDesc] = useState("")
  const [mode, setMode] = useState<"full" | "quick">("full")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    setError("")
    try {
      const res = await api.createAndRunProject(name.trim(), desc.trim(), mode)
      onCreate(res.id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <form
        onSubmit={submit}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-8 shadow-2xl"
      >
        <h2 className="mb-6 text-lg font-semibold text-zinc-100">New Project</h2>

        <label className="mb-1 block text-xs font-medium text-zinc-400">Project name</label>
        <input
          autoFocus
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. SaaS billing platform"
          className="mb-4 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
        />

        <label className="mb-1 block text-xs font-medium text-zinc-400">Description</label>
        <textarea
          value={desc}
          onChange={e => setDesc(e.target.value)}
          placeholder="Describe what you want to build..."
          rows={4}
          className="mb-4 w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-indigo-500"
        />

        {/* Build mode */}
        <label className="mb-1 block text-xs font-medium text-zinc-400">Build Mode</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          {[
            { id: "full", icon: "🏗️", label: "Full Pipeline", sub: "19 stages · Production quality" },
            { id: "quick", icon: "⚡", label: "Quick Build", sub: "~11 stages · Prototype fast" },
          ].map(opt => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setMode(opt.id as "full" | "quick")}
              style={{
                flex: 1, padding: "10px 12px", borderRadius: 10, border: "2px solid",
                borderColor: mode === opt.id ? "var(--color-accent)" : "var(--color-divider)",
                background: mode === opt.id ? "var(--color-accent-dim)" : "transparent",
                cursor: "pointer", textAlign: "left", fontFamily: "var(--font-sans)",
                transition: "all .12s",
              }}
            >
              <div style={{ fontSize: 16, marginBottom: 4 }}>{opt.icon}</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: mode === opt.id ? "var(--color-accent)" : "var(--color-text)" }}>{opt.label}</div>
              <div style={{ fontSize: 10, color: "var(--color-muted)", marginTop: 2 }}>{opt.sub}</div>
            </button>
          ))}
        </div>

        {error && <p className="mb-4 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-400">{error}</p>}

        <div className="flex gap-3">
          <button
            type="button" onClick={onClose}
            className="flex-1 rounded-lg border border-zinc-700 py-2.5 text-sm text-zinc-400 hover:bg-zinc-800"
          >Cancel</button>
          <button
            type="submit" disabled={!name.trim() || loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            {loading && <Spinner size={14} />}
            Create Project
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Settings modal ────────────────────────────────────────────────────────

function SettingsModal({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [form, setForm] = useState({ provider: "", model: "", base_url: "", bedrock_api_key: "", bedrock_region: "" })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    Promise.all([api.getLLMSettings(), api.listProviders()]).then(([s, p]) => {
      setSettings(s)
      setProviders(p.providers)
      setForm({ provider: s.provider, model: s.model, base_url: s.base_url, bedrock_api_key: "", bedrock_region: s.bedrock_region })
    }).catch(() => {})
  }, [])

  const selectedProvider = providers.find(p => p.id === form.provider)

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.updateLLMSettings({ provider: form.provider, model: form.model, bedrock_api_key: form.bedrock_api_key || undefined, bedrock_region: form.bedrock_region || undefined })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900 p-8 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-100">LLM Settings</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">✕</button>
        </div>

        {!settings ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : (
          <form onSubmit={save} className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-400">Provider</label>
              <select
                value={form.provider}
                onChange={e => setForm(f => ({ ...f, provider: e.target.value, model: "" }))}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-indigo-500"
              >
                {providers.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-400">Model</label>
              {selectedProvider ? (
                <select
                  value={form.model}
                  onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-indigo-500"
                >
                  {selectedProvider.models.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              ) : (
                <input
                  value={form.model}
                  onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-indigo-500"
                />
              )}
            </div>

            {selectedProvider?.requires_api_key && (
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-400">
                  API Key {settings.bedrock_api_key_set && <span className="text-emerald-400">(set)</span>}
                </label>
                <input
                  type="password" value={form.bedrock_api_key}
                  onChange={e => setForm(f => ({ ...f, bedrock_api_key: e.target.value }))}
                  placeholder="Leave blank to keep existing"
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-indigo-500"
                />
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button type="button" onClick={onClose} className="flex-1 rounded-lg border border-zinc-700 py-2.5 text-sm text-zinc-400 hover:bg-zinc-800">Cancel</button>
              <button type="submit" disabled={saving} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40">
                {saving ? <Spinner size={14} /> : saved ? "✓ Saved" : "Save"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

// ── Project card ──────────────────────────────────────────────────────────

function ProjectCard({ project, onOpen, onDelete }: {
  project: ProjectSummary
  onOpen: () => void
  onDelete: () => void
}) {
  const [deleting, setDeleting] = useState(false)

  async function del(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`Delete "${project.name}"?`)) return
    setDeleting(true)
    try { await api.deleteProject(project.project_id); onDelete() }
    catch { setDeleting(false) }
  }

  const date = new Date(project.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })

  return (
    <div
      onClick={onOpen}
      className="group relative flex cursor-pointer flex-col justify-between rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-all hover:border-zinc-700 hover:bg-zinc-800/60"
    >
      <div>
        <div className="mb-3 flex items-center gap-2">
          <StatusDot status={project.status} />
          <span className="text-[11px] text-zinc-500">{statusLabel(project.status)}</span>
          {project.mode === "quick" && (
            <span style={{
              fontSize: 10, padding: "1px 6px", borderRadius: 4,
              background: "var(--color-accent-dim)", color: "var(--color-accent)",
              fontWeight: 600, border: "1px solid var(--color-accent-border)",
              lineHeight: "16px",
            }}>⚡ Quick</span>
          )}
        </div>
        <h3 className="mb-1 font-semibold text-zinc-100 line-clamp-1">{project.name}</h3>
        {project.current_stage && (
          <p className="text-xs text-zinc-500">Stage: {project.current_stage.replace(/_/g, " ")}</p>
        )}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-[11px] text-zinc-600">{date}</span>
        <button
          onClick={del}
          disabled={deleting}
          className="rounded-md px-2.5 py-1 text-[11px] text-zinc-600 opacity-0 transition hover:bg-rose-500/10 hover:text-rose-400 group-hover:opacity-100"
        >
          {deleting ? "…" : "Delete"}
        </button>
      </div>
    </div>
  )
}

// ── Projects page ─────────────────────────────────────────────────────────

export function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [ready, setReady] = useState<ReadyStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [list, status] = await Promise.all([api.listProjects(), api.ready()])
      setProjects(list)
      setReady(status)
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="flex h-full flex-col bg-zinc-950 text-zinc-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-zinc-800/60 px-8 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="font-semibold tracking-tight text-zinc-100">AI DevOS</span>
        </div>

        <div className="flex items-center gap-3">
          {/* Health indicator */}
          {ready && (
            <div className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] ${
              ready.status === "ready"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : "border-amber-500/30 bg-amber-500/10 text-amber-400"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${ready.status === "ready" ? "bg-emerald-400" : "bg-amber-400"}`} />
              {ready.status === "ready" ? `${ready.model}` : "Degraded"}
            </div>
          )}
          <button
            onClick={() => setShowSettings(true)}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          >Settings</button>
          <button
            onClick={() => setShowNew(true)}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >+ New Project</button>
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 overflow-y-auto px-8 py-8">
        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Spinner size={24} className="text-indigo-500" />
          </div>
        ) : projects.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-800">
              <svg className="h-8 w-8 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-300">No projects yet</p>
              <p className="mt-1 text-xs text-zinc-600">Create your first project to get started</p>
            </div>
            <button
              onClick={() => setShowNew(true)}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >Create Project</button>
          </div>
        ) : (
          <>
            <div className="mb-6 flex items-center justify-between">
              <h1 className="text-sm font-medium text-zinc-400">{projects.length} project{projects.length !== 1 ? "s" : ""}</h1>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {projects.map(p => (
                <ProjectCard
                  key={p.project_id}
                  project={p}
                  onOpen={() => navigate(`/projects/${p.project_id}`)}
                  onDelete={load}
                />
              ))}
            </div>
          </>
        )}
      </main>

      {showNew && (
        <NewProjectModal
          onClose={() => setShowNew(false)}
          onCreate={id => { setShowNew(false); navigate(`/projects/${id}`) }}
        />
      )}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  )
}

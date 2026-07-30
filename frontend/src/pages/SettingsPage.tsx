import { useEffect, useState } from "react"
import { api, type LLMSettings, type LLMSettingsUpdate, type ProviderInfo } from "../lib/api"

// ── small inline SVG helpers ────────────────────────────────────────────────

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  ) : (
    <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

// ── helpers ──────────────────────────────────────────────────────────────────

function apiKeySetFor(settings: LLMSettings, provider: string): boolean {
  if (provider === "claude")  return settings.claude_api_key_set
  if (provider === "gemini")  return settings.gemini_api_key_set
  if (provider === "bedrock") return settings.bedrock_api_key_set
  return false
}

function apiKeyFieldFor(provider: string): keyof LLMSettingsUpdate | null {
  if (provider === "claude")  return "claude_api_key"
  if (provider === "gemini")  return "gemini_api_key"
  if (provider === "bedrock") return "bedrock_api_key"
  return null
}

// ── shared input style ───────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-divider)",
  background: "var(--color-bg)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
  fontSize: 13,
  outline: "none",
  boxSizing: "border-box",
}

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: ".08em",
  textTransform: "uppercase",
  color: "var(--color-muted)",
  marginBottom: 7,
}

// ── component ────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const [providers, setProviders]   = useState<ProviderInfo[]>([])
  const [current, setCurrent]       = useState<LLMSettings | null>(null)
  const [loading, setLoading]       = useState(true)

  // form state
  const [provider, setProvider]         = useState("")
  const [model, setModel]               = useState("")
  const [apiKey, setApiKey]             = useState("")
  const [showKey, setShowKey]           = useState(false)
  const [ollamaUrl, setOllamaUrl]       = useState("http://localhost:11434")
  const [bedrockRegion, setBedrockRegion] = useState("us-east-1")

  // feedback
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [error, setError]   = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.listProviders(), api.getLLMSettings()])
      .then(([prov, settings]) => {
        setProviders(prov.providers)
        applySettings(settings)
        setCurrent(settings)
      })
      .catch(() => setError("Failed to load settings from server."))
      .finally(() => setLoading(false))
  }, [])

  function applySettings(s: LLMSettings) {
    setProvider(s.provider)
    setModel(s.model)
    setOllamaUrl(s.base_url || "http://localhost:11434")
    setBedrockRegion(s.bedrock_region || "us-east-1")
    setApiKey("")
  }

  function handleProviderChange(id: string) {
    setProvider(id)
    setApiKey("")
    const p = providers.find(p => p.id === id)
    if (p?.default_model) setModel(p.default_model)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const update: LLMSettingsUpdate = { provider, model }
      if (provider === "ollama")  update.base_url = ollamaUrl
      if (provider === "bedrock") update.bedrock_region = bedrockRegion
      if (apiKey) {
        const field = apiKeyFieldFor(provider)
        if (field) (update as Record<string, string>)[field] = apiKey
      }
      const updated = await api.updateLLMSettings(update)
      setCurrent(updated)
      applySettings(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.")
    } finally {
      setSaving(false)
    }
  }

  const selectedProvider = providers.find(p => p.id === provider)

  // ── loading ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--color-muted)", fontSize: 13 }}>
        Loading settings…
      </div>
    )
  }

  // ── render ───────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 660, margin: "0 auto", padding: "36px 24px 60px", color: "var(--color-text)" }}>

      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, letterSpacing: "-.025em", margin: 0 }}>Settings</h1>
        <p style={{ fontSize: 13, color: "var(--color-muted)", marginTop: 4 }}>
          Select the LLM provider and model for all agents. Changes are persisted to <code style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12, background: "rgba(255,255,255,.06)", padding: "1px 5px", borderRadius: 4 }}>backend/.env</code> and take effect immediately — no restart required.
        </p>
      </div>

      {/* Active config pill */}
      {current && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "5px 12px", background: "var(--color-accent-dim)", border: "1px solid var(--color-accent-border)", borderRadius: 999, marginBottom: 24, fontSize: 12 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--color-accent)", flexShrink: 0 }} />
          <span style={{ color: "var(--color-text-muted, var(--color-muted))" }}>Active:</span>
          <span style={{ color: "var(--color-text)", fontWeight: 600 }}>{current.provider}</span>
          <span style={{ color: "var(--color-muted)" }}>/</span>
          <span style={{ color: "var(--color-text)", fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>{current.model}</span>
        </div>
      )}

      <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-divider)", borderRadius: "var(--radius-lg)", padding: 24, display: "flex", flexDirection: "column", gap: 22 }}>

        {/* ── Provider selection ─────────────────────────────────────────── */}
        <section>
          <label style={labelStyle}>Provider</label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {providers.map(p => {
              const active = provider === p.id
              return (
                <button key={p.id} onClick={() => handleProviderChange(p.id)}
                  style={{
                    padding: "10px 12px",
                    borderRadius: "var(--radius-md)",
                    border: active ? "1.5px solid var(--color-accent)" : "1.5px solid var(--color-divider)",
                    background: active ? "var(--color-accent-dim)" : "transparent",
                    color: active ? "var(--color-accent)" : "var(--color-text)",
                    cursor: "pointer",
                    textAlign: "left",
                    fontFamily: "var(--font-sans)",
                    transition: "border-color .12s, background .12s, color .12s",
                  }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{p.label}</span>
                    {active && <CheckIcon />}
                  </div>
                  <div style={{ fontSize: 11, marginTop: 3, color: active ? "var(--color-accent)" : "var(--color-muted)", opacity: active ? 0.85 : 1, lineHeight: 1.4 }}>
                    {p.notes.split(".")[0]}.
                  </div>
                </button>
              )
            })}
          </div>
        </section>

        <div style={{ height: 1, background: "var(--color-divider)" }} />

        {/* ── Model selection ────────────────────────────────────────────── */}
        <section>
          <label style={labelStyle}>Model</label>
          {selectedProvider && selectedProvider.models.length > 0 ? (
            <select value={model} onChange={e => setModel(e.target.value)}
              style={{ ...inputStyle, cursor: "pointer" }}>
              {selectedProvider.models.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder={selectedProvider?.default_model || "model-name"}
              style={inputStyle}
            />
          )}
          {selectedProvider?.notes && (
            <p style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 6, lineHeight: 1.5 }}>
              {selectedProvider.notes}
            </p>
          )}
        </section>

        {/* ── Ollama base URL ────────────────────────────────────────────── */}
        {provider === "ollama" && (
          <section>
            <label style={labelStyle}>Ollama Base URL</label>
            <input
              value={ollamaUrl}
              onChange={e => setOllamaUrl(e.target.value)}
              placeholder="http://localhost:11434"
              style={inputStyle}
            />
            <p style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 6 }}>
              Override if Ollama runs on a non-default host/port or in Docker.
            </p>
          </section>
        )}

        {/* ── Bedrock region ─────────────────────────────────────────────── */}
        {provider === "bedrock" && (
          <section>
            <label style={labelStyle}>AWS Region</label>
            <input
              value={bedrockRegion}
              onChange={e => setBedrockRegion(e.target.value)}
              placeholder="us-east-1"
              style={inputStyle}
            />
          </section>
        )}

        {/* ── API key ────────────────────────────────────────────────────── */}
        {selectedProvider?.requires_api_key && (
          <section>
            <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <span>API Key</span>
              {current && apiKeySetFor(current, provider) && (
                <span style={{ fontWeight: 500, textTransform: "none", fontSize: 11, color: "var(--color-success)", letterSpacing: 0 }}>
                  ✓ currently set
                </span>
              )}
            </label>
            <div style={{ position: "relative" }}>
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={current && apiKeySetFor(current, provider) ? "Enter new key to rotate…" : "sk-…"}
                style={{ ...inputStyle, paddingRight: 36, fontFamily: "var(--font-mono, monospace)" }}
              />
              <button
                onClick={() => setShowKey(v => !v)}
                title={showKey ? "Hide key" : "Show key"}
                style={{ position: "absolute", right: 9, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--color-muted)", padding: 2, display: "flex" }}>
                <EyeIcon open={showKey} />
              </button>
            </div>
            <p style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 6 }}>
              Stored in <code style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11, background: "rgba(255,255,255,.06)", padding: "1px 4px", borderRadius: 3 }}>backend/.env</code>. Never logged or forwarded.
              {!apiKey && current && apiKeySetFor(current, provider) && " Leave blank to keep the existing key."}
            </p>
          </section>
        )}

        {/* ── Error ──────────────────────────────────────────────────────── */}
        {error && (
          <div style={{ padding: "9px 12px", background: "rgba(239,68,68,.08)", border: "1px solid rgba(239,68,68,.25)", borderRadius: "var(--radius-md)", fontSize: 13, color: "#f87171" }}>
            {error}
          </div>
        )}

        {/* ── Save ───────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: "9px 22px",
              borderRadius: "var(--radius-md)",
              border: "none",
              cursor: saving ? "default" : "pointer",
              background: saved ? "var(--color-success, #22c55e)" : "var(--color-accent)",
              color: "#fff",
              fontFamily: "var(--font-sans)",
              fontSize: 13,
              fontWeight: 600,
              opacity: saving ? 0.7 : 1,
              transition: "background .2s, opacity .15s",
              display: "flex",
              alignItems: "center",
              gap: 7,
            }}>
            {saving ? "Saving…" : saved ? <><CheckIcon /> Saved</> : "Save Settings"}
          </button>
          {saved && (
            <span style={{ fontSize: 12, color: "var(--color-success, #22c55e)" }}>
              LLM reconfigured — agents will use <strong>{provider}/{model}</strong> for the next run.
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

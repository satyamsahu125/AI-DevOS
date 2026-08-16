import { useEffect, useState } from "react"
import { api, type LLMSettings, type LLMSettingsUpdate, type ProviderInfo } from "../lib/api"

export default function SettingsPage() {
  const [settings, setSettings] = useState<LLMSettings | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // Form state
  const [provider, setProvider] = useState("")
  const [model, setModel] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [bedrockRegion, setBedrockRegion] = useState("")
  const [claudeKey, setClaudeKey] = useState("")
  const [geminiKey, setGeminiKey] = useState("")
  const [bedrockKey, setBedrockKey] = useState("")
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getLLMSettings(),
      api.listProviders().then(r => r.providers),
    ]).then(([s, ps]) => {
      setSettings(s)
      setProviders(ps)
      setProvider(s.provider)
      setModel(s.model)
      setBaseUrl(s.base_url ?? "")
      setBedrockRegion(s.bedrock_region ?? "")
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const activeProvider = providers.find(p => p.id === provider)

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(false)
    try {
      const update: LLMSettingsUpdate = { provider, model }
      if (baseUrl) update.base_url = baseUrl
      if (bedrockRegion) update.bedrock_region = bedrockRegion
      if (claudeKey) update.claude_api_key = claudeKey
      if (geminiKey) update.gemini_api_key = geminiKey
      if (bedrockKey) update.bedrock_api_key = bedrockKey
      const updated = await api.updateLLMSettings(update)
      setSettings(updated)
      setSuccess(true)
      setClaudeKey("")
      setGeminiKey("")
      setBedrockKey("")
    } catch (err: any) {
      setError(err.message ?? "Failed to save settings")
    } finally {
      setSaving(false)
    }
  }

  const toggleShow = (key: string) => setShowKeys(s => ({ ...s, [key]: !s[key] }))

  if (loading) return (
    <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
      <div className="spinner spinner-lg" />
    </div>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="page-header">
        <div className="page-title">LLM Configuration</div>
        {settings && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="badge badge-accent">{settings.provider}</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>{settings.model}</span>
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "24px" }}>
        <form onSubmit={handleSave} style={{ maxWidth: 580, display: "flex", flexDirection: "column", gap: 24 }}>

          {/* Provider selection */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 12 }}>Provider</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 8 }}>
              {providers.map(p => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { setProvider(p.id); setModel(p.default_model ?? "") }}
                  style={{
                    padding: "10px 12px",
                    borderRadius: "var(--radius-md)",
                    border: `1px solid ${provider === p.id ? "var(--accent-border)" : "var(--border)"}`,
                    background: provider === p.id ? "var(--accent-lo)" : "var(--surface-2)",
                    color: provider === p.id ? "var(--accent-hi)" : "var(--text-muted)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "all 120ms",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.label}</div>
                  {p.notes && <div style={{ fontSize: 10, opacity: 0.6, marginTop: 2 }}>{p.notes}</div>}
                </button>
              ))}
            </div>
          </div>

          {/* Model */}
          <div>
            <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Model
            </label>
            {activeProvider?.models && activeProvider.models.length > 0 ? (
              <select
                className="input"
                value={model}
                onChange={e => setModel(e.target.value)}
                style={{ background: "var(--surface-3)" }}
              >
                {activeProvider.models.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            ) : (
              <input
                className="input"
                value={model}
                onChange={e => setModel(e.target.value)}
                placeholder="e.g. llama3.2:latest"
              />
            )}
          </div>

          {/* Ollama base URL */}
          {provider === "ollama" && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                Base URL
              </label>
              <input
                className="input"
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                placeholder="http://localhost:11434"
              />
            </div>
          )}

          {/* Bedrock region */}
          {provider === "bedrock" && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
                AWS Region
              </label>
              <input
                className="input"
                value={bedrockRegion}
                onChange={e => setBedrockRegion(e.target.value)}
                placeholder="us-east-1"
              />
            </div>
          )}

          {/* API keys */}
          {(provider === "claude" || provider === "anthropic") && (
            <KeyField
              label="Claude API Key"
              value={claudeKey}
              onChange={setClaudeKey}
              isSet={settings?.claude_api_key_set ?? false}
              show={showKeys["claude"] ?? false}
              onToggle={() => toggleShow("claude")}
              placeholder="sk-ant-..."
            />
          )}

          {provider === "gemini" && (
            <KeyField
              label="Gemini API Key"
              value={geminiKey}
              onChange={setGeminiKey}
              isSet={settings?.gemini_api_key_set ?? false}
              show={showKeys["gemini"] ?? false}
              onToggle={() => toggleShow("gemini")}
              placeholder="AIza..."
            />
          )}

          {provider === "bedrock" && (
            <KeyField
              label="Bedrock API Key"
              value={bedrockKey}
              onChange={setBedrockKey}
              isSet={settings?.bedrock_api_key_set ?? false}
              show={showKeys["bedrock"] ?? false}
              onToggle={() => toggleShow("bedrock")}
              placeholder="AWS access key"
            />
          )}

          {/* Messages */}
          {error && <div className="error-banner">{error}</div>}
          {success && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", background: "var(--success-lo)", border: "1px solid rgba(34,197,94,0.2)", borderRadius: "var(--radius-md)", fontSize: 13, color: "var(--success)" }}>
              ✓ Settings saved successfully
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={saving} style={{ width: "fit-content" }}>
            {saving && <div className="spinner spinner-sm" style={{ borderTopColor: "#fff" }} />}
            Save Settings
          </button>
        </form>
      </div>
    </div>
  )
}

function KeyField({
  label, value, onChange, isSet, show, onToggle, placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  isSet: boolean
  show: boolean
  onToggle: () => void
  placeholder: string
}) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <label style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)" }}>{label}</label>
        {isSet && <span className="badge badge-success">Currently set</span>}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          className="input"
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={isSet ? "Enter new key to rotate…" : placeholder}
          style={{ flex: 1 }}
        />
        <button type="button" className="btn btn-secondary" onClick={onToggle} style={{ flexShrink: 0 }}>
          {show ? "Hide" : "Show"}
        </button>
      </div>
    </div>
  )
}

import { useEffect, useState } from "react"
import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import { api, type LLMSettings, type ProviderInfo, type ReadyStatus } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function SettingsPage() {
  const [ready, setReady] = useState<ReadyStatus | null>(null)
  const [llm, setLlm] = useState<LLMSettings | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])

  const [providerId, setProviderId] = useState("")
  const [model, setModel] = useState("")
  const [region, setRegion] = useState("us-east-1")
  const [apiKey, setApiKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  useEffect(() => {
    api.ready().then(setReady).catch(() => setReady(null))
    refreshLLMSettings()
    api.listProviders().then((res) => setProviders(res.providers)).catch(() => setProviders([]))
  }, [])

  function refreshLLMSettings() {
    api.getLLMSettings().then((settings) => {
      setLlm(settings)
      setProviderId(settings.provider)
      setModel(settings.model)
      setRegion(settings.bedrock_region)
    }).catch(() => setLlm(null))
  }

  const activeProvider = providers.find((p) => p.id === providerId)

  async function handleSave() {
    setSaving(true)
    setSaveMessage(null)
    try {
      await api.updateLLMSettings({
        provider: providerId,
        model,
        ...(providerId === "bedrock" ? { bedrock_region: region } : {}),
        ...(providerId === "bedrock" && apiKey ? { bedrock_api_key: apiKey } : {}),
      })
      setApiKey("")
      refreshLLMSettings()
      setSaveMessage("Saved.")
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to save.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Backend connectivity, model status, and LLM provider.</p>
      </header>

      <div className="flex flex-col gap-6 max-w-md">
        <Card>
          <CardHeader>
            <CardTitle>Backend Health</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {!ready && <p className="text-muted-foreground">Checking…</p>}
            {ready && (
              <>
                <Row label="Status" ok={ready.status === "ready"} value={ready.status} />
                <Row label="Ollama" ok={ready.ollama === "reachable"} value={ready.ollama} />
                <Row label="Model" ok={ready.model_available} value={ready.model} />
                <Row label="Database" ok={ready.database === "connected"} value={ready.database} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>LLM Provider</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            {llm && (
              <p className="text-xs text-muted-foreground">
                Currently active: <span className="font-medium text-foreground">{llm.provider}</span> / {llm.model}
              </p>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-muted-foreground">Provider</label>
              <div className="flex gap-2">
                {providers.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setProviderId(p.id)}
                    className={`flex-1 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                      providerId === p.id ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-accent/50"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {providerId === "ollama" && activeProvider && activeProvider.models.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground">Model (detected on local Ollama)</label>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="rounded-md border border-border bg-background px-3 py-2 text-xs"
                >
                  {activeProvider.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {providerId === "bedrock" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Model ID (from your Bedrock model catalog, e.g. the Qwen3 Coder 480B entry)
                  </label>
                  <Input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="e.g. qwen.qwen3-coder-480b-a35b-v1:0"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Region</label>
                  <Input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    API Key {llm?.bedrock_api_key_set && <span className="text-emerald-500">(already set -- leave blank to keep it)</span>}
                  </label>
                  <Input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Bedrock long-term or short-term API key"
                  />
                </div>
              </>
            )}

            <div className="flex items-center gap-3">
              <Button onClick={handleSave} disabled={saving} size="sm">
                {saving && <Loader2 className="size-3.5 animate-spin" />}
                Save
              </Button>
              {saveMessage && <span className="text-xs text-muted-foreground">{saveMessage}</span>}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Row({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border pb-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={ok ? "success" : "destructive"}>
        {ok ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
        {value}
      </Badge>
    </div>
  )
}

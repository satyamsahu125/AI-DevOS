import { useEffect, useRef, useState } from "react"
import { AlertCircle, FileText, Info, Terminal, TriangleAlert, History, CheckCircle, Clock } from "lucide-react"

import { api, STAGE_LABELS, type ArtifactSummary, type LogEvent, type ArtifactHistoryItem } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"

const LEVEL_ICON = { info: Info, warning: TriangleAlert, error: AlertCircle }
const LEVEL_COLOR = { info: "text-muted-foreground", warning: "text-warning font-medium", error: "text-destructive font-medium" }

function LiveOutput({ logs }: { logs: LogEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length])

  return (
    <ScrollArea className="h-full px-4 py-2">
      <div className="flex flex-col gap-1 font-mono text-xs">
        {logs.length === 0 && <p className="text-muted-foreground py-4 text-center">No build events logged yet.</p>}
        {logs.map((log) => {
          const Icon = LEVEL_ICON[log.level]
          return (
            <div key={log.id} className={cn("flex items-start gap-2 py-0.5 border-b border-border/20 last:border-0", LEVEL_COLOR[log.level])}>
              <Icon className="mt-0.5 size-3 shrink-0" />
              <span className="shrink-0 text-[10px] text-muted-foreground/60">
                {new Date(log.created_at).toLocaleTimeString()}
              </span>
              <span className="shrink-0 font-semibold text-foreground/80">[{STAGE_LABELS[log.stage as keyof typeof STAGE_LABELS] ?? log.stage}]</span>
              <span className="leading-relaxed">{log.message}</span>
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  )
}

function ArtifactsTab({ projectId, artifacts }: { projectId: string; artifacts: ArtifactSummary[] }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [history, setHistory] = useState<ArtifactHistoryItem[]>([])
  const [activeAttemptIndex, setActiveAttemptIndex] = useState<number>(0)
  const [loading, setLoading] = useState(false)

  async function open(stage: string) {
    setSelected(stage)
    setLoading(true)
    try {
      const items = await api.getArtifactHistory(projectId, stage)
      setHistory(items)
      setActiveAttemptIndex(items.length > 0 ? items.length - 1 : 0)
    } catch {
      const detail = await api.getArtifact(projectId, stage)
      setHistory([{ attempt: detail.attempt, content: detail.content, structured: detail.structured, approved: true }])
      setActiveAttemptIndex(0)
    } finally {
      setLoading(false)
    }
  }

  const currentItem = history[activeAttemptIndex]

  return (
    <div className="flex h-full">
      <div className="w-56 shrink-0 border-r border-border bg-card/20">
        <ScrollArea className="h-full p-2">
          {artifacts.length === 0 && <p className="p-3 text-xs text-muted-foreground">No approved artifacts generated yet.</p>}
          {artifacts.map((artifact) => (
            <button
              key={artifact.stage}
              onClick={() => open(artifact.stage)}
              className={cn(
                "flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-xs transition-colors hover:bg-accent/60 mb-1",
                selected === artifact.stage ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground",
              )}
            >
              <div className="flex items-center gap-2 truncate">
                <FileText className="size-3.5 shrink-0 text-primary" />
                <span className="truncate">{STAGE_LABELS[artifact.stage as keyof typeof STAGE_LABELS] ?? artifact.stage}</span>
              </div>
              <span className="text-[10px] font-mono text-muted-foreground/70">v{artifact.attempt}</span>
            </button>
          ))}
        </ScrollArea>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {selected && history.length > 0 && (
          <div className="flex items-center justify-between border-b border-border bg-card/30 px-4 py-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-semibold">{STAGE_LABELS[selected as keyof typeof STAGE_LABELS] ?? selected}</span>
              <Badge variant="outline" className="text-[10px]">
                {history.length} Attempt{history.length > 1 ? "s" : ""}
              </Badge>
            </div>

            <div className="flex items-center gap-1.5">
              <History className="size-3 text-muted-foreground" />
              {history.map((item, idx) => (
                <button
                  key={item.attempt}
                  onClick={() => setActiveAttemptIndex(idx)}
                  className={cn(
                    "px-2 py-0.5 rounded text-[11px] font-mono transition-colors flex items-center gap-1",
                    activeAttemptIndex === idx
                      ? "bg-primary text-primary-foreground font-semibold"
                      : "bg-accent/50 hover:bg-accent text-muted-foreground",
                  )}
                >
                  Attempt #{item.attempt}
                  {item.approved ? <CheckCircle className="size-2.5 text-emerald-400" /> : <Clock className="size-2.5 text-amber-400" />}
                </button>
              ))}
            </div>
          </div>
        )}

        <ScrollArea className="flex-1 p-4">
          {!selected && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-muted-foreground py-12">
              <FileText className="size-6 text-muted-foreground/40" />
              Select an artifact from the list to preview specifications & documentation.
            </div>
          )}
          {selected && loading && <p className="text-xs text-muted-foreground">Loading artifact history…</p>}
          {selected && !loading && currentItem && (
            <pre className="text-xs leading-relaxed whitespace-pre-wrap font-mono text-foreground/90 bg-card/30 p-4 rounded-lg border border-border/60">
              <code>{currentItem.content}</code>
            </pre>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}

interface BottomPanelProps {
  projectId: string
  logs: LogEvent[]
  artifacts: ArtifactSummary[]
}

export function BottomPanel({ projectId, logs, artifacts }: BottomPanelProps) {
  return (
    <div className="flex h-full flex-col bg-card/30">
      <Tabs defaultValue="logs" className="flex h-full flex-col gap-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-1.5 bg-card/50">
          <TabsList className="h-8">
            <TabsTrigger value="logs" className="text-xs py-1">
              <Terminal className="size-3.5 mr-1.5 text-primary" /> Live Output Log
              {logs.length > 0 && (
                <Badge variant="muted" className="ml-1.5 text-[10px]">
                  {logs.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="artifacts" className="text-xs py-1">
              <FileText className="size-3.5 mr-1.5 text-emerald-400" /> Approved Artifacts
              {artifacts.length > 0 && (
                <Badge variant="muted" className="ml-1.5 text-[10px]">
                  {artifacts.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="logs" className="flex-1 overflow-hidden m-0">
          <LiveOutput logs={logs} />
        </TabsContent>
        <TabsContent value="artifacts" className="flex-1 overflow-hidden m-0">
          <ArtifactsTab projectId={projectId} artifacts={artifacts} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

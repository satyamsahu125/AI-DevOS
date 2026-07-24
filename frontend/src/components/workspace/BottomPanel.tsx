import { useEffect, useRef, useState } from "react"
import { AlertCircle, FileText, Info, Terminal, TriangleAlert } from "lucide-react"

import { api, STAGE_LABELS, type ArtifactSummary, type LogEvent } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"

const LEVEL_ICON = { info: Info, warning: TriangleAlert, error: AlertCircle }
const LEVEL_COLOR = { info: "text-muted-foreground", warning: "text-warning", error: "text-destructive" }

function LiveOutput({ logs }: { logs: LogEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length])

  return (
    <ScrollArea className="h-full px-4 py-2">
      <div className="flex flex-col gap-1 font-mono text-xs">
        {logs.length === 0 && <p className="text-muted-foreground">No build events yet.</p>}
        {logs.map((log) => {
          const Icon = LEVEL_ICON[log.level]
          return (
            <div key={log.id} className={cn("flex items-start gap-2", LEVEL_COLOR[log.level])}>
              <Icon className="mt-0.5 size-3 shrink-0" />
              <span className="shrink-0 text-muted-foreground/70">
                {new Date(log.created_at).toLocaleTimeString()}
              </span>
              <span className="shrink-0 font-semibold">[{log.stage}]</span>
              <span>{log.message}</span>
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
  const [content, setContent] = useState<string | null>(null)

  async function open(stage: string) {
    setSelected(stage)
    setContent(null)
    const detail = await api.getArtifact(projectId, stage)
    setContent(detail.content)
  }

  return (
    <div className="flex h-full">
      <div className="w-56 shrink-0 border-r border-border">
        <ScrollArea className="h-full p-2">
          {artifacts.length === 0 && <p className="p-2 text-xs text-muted-foreground">No approved documents yet.</p>}
          {artifacts.map((artifact) => (
            <button
              key={artifact.stage}
              onClick={() => open(artifact.stage)}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent/60",
                selected === artifact.stage && "bg-accent text-accent-foreground",
              )}
            >
              <FileText className="size-3 shrink-0" />
              {STAGE_LABELS[artifact.stage as keyof typeof STAGE_LABELS] ?? artifact.stage}
            </button>
          ))}
        </ScrollArea>
      </div>
      <ScrollArea className="flex-1 p-4">
        {!selected && <p className="text-xs text-muted-foreground">Select a document to preview it.</p>}
        {selected && (
          <pre className="text-xs leading-relaxed whitespace-pre-wrap">
            <code>{content ?? "Loading…"}</code>
          </pre>
        )}
      </ScrollArea>
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
        <div className="flex items-center border-b border-border px-3 py-1.5">
          <TabsList>
            <TabsTrigger value="logs">
              <Terminal /> Live Output
            </TabsTrigger>
            <TabsTrigger value="artifacts">
              <FileText /> Artifacts
              {artifacts.length > 0 && (
                <Badge variant="muted" className="ml-1">
                  {artifacts.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="logs" className="flex-1 overflow-hidden">
          <LiveOutput logs={logs} />
        </TabsContent>
        <TabsContent value="artifacts" className="flex-1 overflow-hidden">
          <ArtifactsTab projectId={projectId} artifacts={artifacts} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

import { useMemo } from "react"
import { Loader2 } from "lucide-react"

import { STAGE_LABELS, type LogEvent } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface StageBlock {
  stage: string
  events: LogEvent[]
}

function groupByStage(events: LogEvent[]): StageBlock[] {
  const blocks: StageBlock[] = []
  for (const event of events) {
    const last = blocks[blocks.length - 1]
    if (last && last.stage === event.stage) {
      last.events.push(event)
    } else {
      blocks.push({ stage: event.stage, events: [event] })
    }
  }
  return blocks
}

function blockOutcome(events: LogEvent[]): "running" | "approved" | "failed" {
  const last = events[events.length - 1]
  if (last.message.includes("approved")) return "approved"
  if (last.level === "error") return "failed"
  return "running"
}

interface ChatPanelProps {
  logs: LogEvent[]
  onRetryStage: (stage: string) => void
}

export function ChatPanel({ logs, onRetryStage }: ChatPanelProps) {
  const blocks = useMemo(() => groupByStage(logs), [logs])

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex items-center border-b border-border px-6 py-4">
        <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Chat</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {blocks.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No build activity yet. Press Start Build to watch the AI team work through all 12 stages live.
          </p>
        )}

        <div className="flex flex-col gap-3">
          {blocks.map((block, i) => {
            const outcome = blockOutcome(block.events)
            return (
              <div key={i} className="rounded-xl border border-border bg-card/30 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {outcome === "running" && <Loader2 className="size-3.5 animate-spin text-primary" />}
                    {STAGE_LABELS[block.stage as keyof typeof STAGE_LABELS] ?? block.stage}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={outcome === "approved" ? "success" : outcome === "failed" ? "destructive" : "warning"}>
                      {outcome === "approved" ? "Approved" : outcome === "failed" ? "Failed" : "Working…"}
                    </Badge>
                    {outcome === "failed" && (
                      <Button size="sm" variant="outline" onClick={() => onRetryStage(block.stage)}>
                        Retry stage
                      </Button>
                    )}
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  {block.events.map((event) => (
                    <p
                      key={event.id}
                      className={
                        event.level === "error"
                          ? "text-xs text-destructive"
                          : event.level === "warning"
                            ? "text-xs text-warning"
                            : "text-xs text-muted-foreground"
                      }
                    >
                      {event.message}
                    </p>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

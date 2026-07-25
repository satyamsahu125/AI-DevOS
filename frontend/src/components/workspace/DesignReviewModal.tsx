import { useEffect, useState } from "react"
import { Check, Edit3, Loader2, Sparkles, AlertCircle } from "lucide-react"

import { api, type DesignReviewData } from "@/lib/api"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ScrollArea } from "@/components/ui/scroll-area"

interface DesignReviewModalProps {
  projectId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onActionCompleted?: () => void
}

export function DesignReviewModal({ projectId, open, onOpenChange, onActionCompleted }: DesignReviewModalProps) {
  const [data, setData] = useState<DesignReviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState("")
  const [isRevision, setIsRevision] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open && projectId) {
      setLoading(true)
      setError(null)
      api
        .getDesignReview(projectId)
        .then((res) => setData(res))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load design review"))
        .finally(() => setLoading(false))
    }
  }, [open, projectId])

  async function handleApprove() {
    setSubmitting(true)
    setError(null)
    try {
      await api.postDesignReview(projectId, true)
      await api.continueWorkflow(projectId)
      onOpenChange(false)
      if (onActionCompleted) onActionCompleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve design")
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRequestRevision() {
    if (!feedback.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.postDesignReview(projectId, false, feedback)
      await api.continueWorkflow(projectId)
      onOpenChange(false)
      if (onActionCompleted) onActionCompleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to request design revision")
    } finally {
      setSubmitting(false)
    }
  }

  const design = data?.design || {}

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-0 overflow-hidden border-border bg-background">
        <DialogHeader className="p-6 pb-4 border-b border-border bg-card/40">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
                <Sparkles className="size-4 animate-pulse" />
              </div>
              <div>
                <DialogTitle className="text-base font-semibold">Human Action Required: System Design Review</DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground">
                  Iteration #{data?.review_iteration || 1} &middot; Perform human review & action to approve system design before pipeline continues.
                </DialogDescription>
              </div>
            </div>
            <Badge variant="warning" className="bg-amber-500/20 text-amber-300 border-amber-500/40">
              Human Action Required
            </Badge>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-hidden p-6">
          {loading ? (
            <div className="flex h-64 items-center justify-center text-xs text-muted-foreground">
              <Loader2 className="mr-2 size-4 animate-spin" /> Loading design specification…
            </div>
          ) : error ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-center text-xs text-destructive">
              <AlertCircle className="size-6" />
              <p>{error}</p>
            </div>
          ) : (
            <Tabs defaultValue="overview" className="flex h-full flex-col">
              <TabsList className="mb-4">
                <TabsTrigger value="overview">Overview & Requirements</TabsTrigger>
                <TabsTrigger value="architecture">Architecture & Components</TabsTrigger>
                <TabsTrigger value="raw">Raw Design Spec</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="flex-1 overflow-hidden">
                <ScrollArea className="h-[40vh] pr-4">
                  <div className="flex flex-col gap-4 text-xs">
                    <div className="rounded-lg border border-border bg-card/50 p-4">
                      <h4 className="font-semibold text-foreground mb-1">Project Objective</h4>
                      <p className="text-muted-foreground leading-relaxed">
                        {String(design.project_name || design.title || "Project Design Spec")}
                      </p>
                    </div>

                    {design.summary ? (
                      <div className="rounded-lg border border-border bg-card/50 p-4">
                        <h4 className="font-semibold text-foreground mb-1">Executive Summary</h4>
                        <p className="text-muted-foreground leading-relaxed">{String(design.summary)}</p>
                      </div>
                    ) : null}

                    {design.tech_stack ? (
                      <div className="rounded-lg border border-border bg-card/50 p-4">
                        <h4 className="font-semibold text-foreground mb-2">Technology Stack</h4>
                        <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-muted-foreground">
                          {typeof design.tech_stack === "string"
                            ? design.tech_stack
                            : JSON.stringify(design.tech_stack, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </ScrollArea>
              </TabsContent>

              <TabsContent value="architecture" className="flex-1 overflow-hidden">
                <ScrollArea className="h-[40vh] pr-4">
                  <div className="flex flex-col gap-4 text-xs">
                    {design.modules ? (
                      <div className="rounded-lg border border-border bg-card/50 p-4">
                        <h4 className="font-semibold text-foreground mb-2">Modules Breakdown</h4>
                        <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-muted-foreground">
                          {typeof design.modules === "string"
                            ? design.modules
                            : JSON.stringify(design.modules, null, 2)}
                        </pre>
                      </div>
                    ) : null}

                    {design.components ? (
                      <div className="rounded-lg border border-border bg-card/50 p-4">
                        <h4 className="font-semibold text-foreground mb-2">Frontend Components</h4>
                        <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-muted-foreground">
                          {typeof design.components === "string"
                            ? design.components
                            : JSON.stringify(design.components, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </ScrollArea>
              </TabsContent>

              <TabsContent value="raw" className="flex-1 overflow-hidden">
                <ScrollArea className="h-[40vh] pr-4">
                  <pre className="text-[11px] leading-relaxed whitespace-pre-wrap font-mono text-muted-foreground bg-card/50 p-4 rounded-lg border border-border">
                    <code>{JSON.stringify(design, null, 2)}</code>
                  </pre>
                </ScrollArea>
              </TabsContent>
            </Tabs>
          )}
        </div>

        <div className="border-t border-border bg-card/50 p-4 flex flex-col gap-3">
          {isRevision ? (
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-muted-foreground">
                Describe desired changes or feedback for revision:
              </label>
              <Textarea
                rows={2}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="e.g., Add JWT auth endpoint, change UI layout to dark glassmorphism, use Tailwind grid..."
                className="text-xs"
              />
              <div className="flex justify-end gap-2 mt-1">
                <Button size="sm" variant="ghost" onClick={() => setIsRevision(false)} disabled={submitting}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleRequestRevision}
                  disabled={submitting || !feedback.trim()}
                >
                  {submitting && <Loader2 className="mr-1.5 size-3 animate-spin" />}
                  Submit Revision Request
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <Button size="sm" variant="outline" onClick={() => setIsRevision(true)} disabled={submitting}>
                <Edit3 className="mr-1.5 size-3.5" /> Request Revision
              </Button>
              <Button size="sm" variant="default" onClick={handleApprove} disabled={submitting}>
                {submitting ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <Check className="mr-1.5 size-3.5" />}
                Approve Design & Start Sprints
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

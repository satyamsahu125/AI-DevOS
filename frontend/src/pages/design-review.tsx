import { useState, useEffect } from "react"
import { Puck } from "@measured/puck"
import "@measured/puck/puck.css"
import { puckConfig } from "@/puck/config"
import { designArtifactToPuck, puckToDesignArtifact } from "@/puck/design-converter"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"

export default function DesignReviewPage({ projectId }: { projectId: string }) {
  const [design, setDesign] = useState<any>(null)
  const [puckData, setPuckData] = useState<any>(null)
  const [feedback, setFeedback] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [status, setStatus] = useState<"idle" | "approved" | "revised">("idle")

  useEffect(() => {
    if (!projectId) return
    fetch(`/api/workflow/${projectId}/design-review`)
      .then((r) => r.json())
      .then((data) => {
        setDesign(data.design)
        if (data.design) {
          setPuckData(designArtifactToPuck(data.design))
        }
      })
      .catch((err) => console.error("Failed to fetch design review:", err))
  }, [projectId])

  const handleApprove = async () => {
    setSubmitting(true)
    const modifiedDesign = puckToDesignArtifact(puckData, design)

    await fetch(`/api/workflow/${projectId}/design-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approved: true,
        feedback: feedback || "Approved",
        modified_design: modifiedDesign,
      }),
    })
    setStatus("approved")
    setSubmitting(false)
  }

  const handleRequestChanges = async () => {
    setSubmitting(true)
    await fetch(`/api/workflow/${projectId}/design-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approved: false,
        feedback: feedback,
      }),
    })
    setStatus("revised")
    setSubmitting(false)
  }

  if (!puckData) return <div className="p-8 text-center text-sm text-muted-foreground">Loading design...</div>
  if (status === "approved")
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <Badge className="mb-4">✓ Design Approved</Badge>
          <p className="text-sm text-muted-foreground">Sprint planning is starting...</p>
        </div>
      </div>
    )

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b bg-background z-10">
        <div>
          <h1 className="font-semibold text-lg">Design Review</h1>
          <p className="text-sm text-muted-foreground">
            Drag components to rearrange. Click to edit text and settings.
          </p>
        </div>
        <Badge variant="outline">Iteration {design?.review_iteration || 1}</Badge>
      </div>

      {/* Puck Editor — full canvas */}
      <div className="flex-1 overflow-hidden">
        <Puck
          config={puckConfig}
          data={puckData}
          onChange={setPuckData}
          overrides={{
            // Hide the publish button (we handle this ourselves). Puck's
            // override must return an element, so render an empty fragment
            // rather than null.
            header: () => <></>,
          }}
        />
      </div>

      {/* Bottom action bar */}
      <div className="border-t p-4 bg-background">
        <div className="flex gap-4 items-start max-w-4xl mx-auto">
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Optional: describe any changes you want (e.g. 'make it dark mode', 'add a pricing section', 'change nav to sidebar')"
            className="flex-1 resize-none"
            rows={2}
          />
          <div className="flex flex-col gap-2">
            <Button onClick={handleApprove} disabled={submitting} className="w-40">
              ✓ Approve Design
            </Button>
            <Button
              variant="outline"
              onClick={handleRequestChanges}
              disabled={submitting || !feedback}
              className="w-40"
            >
              ↩ Request Changes
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Your drag-and-drop modifications are automatically saved. Click Approve to generate code from this design.
        </p>
      </div>
    </div>
  )
}

export { DesignReviewPage }

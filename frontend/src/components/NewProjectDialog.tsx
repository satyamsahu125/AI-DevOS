import { useState } from "react"
import { Loader2 } from "lucide-react"

import { api, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface NewProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (projectId: string) => void
}

export function NewProjectDialog({ open, onOpenChange, onCreated }: NewProjectDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate() {
    if (!name.trim() || !description.trim()) {
      setError("Both a name and a description are required.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      // NOTE: this call runs the first pipeline stage synchronously and can
      // take 30-120+ seconds -- the spinner below reflects that honestly.
      const result = await api.createProject(name.trim(), description.trim())
      onOpenChange(false)
      setName("")
      setDescription("")
      onCreated(result.project.project_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !submitting && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Project</DialogTitle>
          <DialogDescription>
            Describe what you want built. This kicks off the Strategic Review and Product Owner stages immediately.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Project name</label>
            <Input placeholder="RecipeBox" value={name} onChange={(e) => setName(e.target.value)} disabled={submitting} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">What should it do?</label>
            <Textarea
              placeholder="Build a recipe sharing app where users can post recipes with photos and rate other users' recipes."
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={submitting}>
            {submitting && <Loader2 className="animate-spin" />}
            {submitting ? "Starting Product Owner…" : "Create Project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

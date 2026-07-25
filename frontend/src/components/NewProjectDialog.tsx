import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"

import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface NewProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (projectId: string) => void
  initialDescription?: string
}

export function NewProjectDialog({ open, onOpenChange, onCreated, initialDescription }: NewProjectDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      if (initialDescription) {
        setDescription(initialDescription)
        const firstWords = initialDescription.split(" ").slice(0, 3).join(" ").replace(/[^a-zA-Z0-9 ]/g, "")
        setName(firstWords || "New Project")
      }
    } else {
      setError(null)
    }
  }, [open, initialDescription])

  async function handleCreate() {
    if (!name.trim() || !description.trim()) {
      setError("Both a project name and a description are required.")
      return
    }

    const projName = name.trim()
    const projDesc = description.trim()

    // Immediately close the dialog modal as requested by the user
    onOpenChange(false)
    setName("")
    setDescription("")

    try {
      // Create project & launch background AI pipeline
      const result = await api.createProject(projName, projDesc)
      if (result?.project?.project_id) {
        onCreated(result.project.project_id)
      }
    } catch (err) {
      console.error("Failed to create project:", err)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg border-border/80 bg-slate-950/95 backdrop-blur-xl shadow-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2.5 mb-1">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/20 text-primary border border-primary/30">
              <Sparkles className="size-4" />
            </div>
            <DialogTitle className="text-base font-semibold text-foreground">Initialize Autonomous AI Agent Team</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-muted-foreground leading-relaxed">
            Specify your project details. The modal will close immediately and transition you straight to the AI DevOS Workspace.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Project Name</label>
            <Input
              placeholder="e.g. MarkdownStudio"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-xs bg-slate-900/60 border-border/60 focus:border-primary"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Application Requirements & Prompt</label>
            <Textarea
              placeholder="Describe the application features, API routes, UI layout preferences, or target framework..."
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="text-xs leading-relaxed bg-slate-900/60 border-border/60 focus:border-primary"
            />
          </div>
          {error && <p className="text-xs text-destructive font-medium">{error}</p>}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleCreate} disabled={!name.trim() || !description.trim()} className="bg-primary hover:bg-primary/90">
            <Sparkles className="mr-1.5 size-3.5" /> Initialize AI Team
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

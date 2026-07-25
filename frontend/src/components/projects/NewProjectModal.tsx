import { motion, AnimatePresence } from "framer-motion"
import { useState } from "react"
import { X, Sparkles, Paperclip, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useNavigate } from "react-router-dom"

interface NewProjectModalProps {
  open: boolean
  onClose: () => void
}

export function NewProjectModal({ open, onClose }: NewProjectModalProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleCreate = async () => {
    if (!name || !description) return
    setLoading(true)

    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      })
      const data = await res.json()
      const projectId = data.project?.project_id || data.project_id

      // Start pipeline
      await fetch("/api/workflow/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          request: description,
        }),
      })

      onClose()
      navigate(`/projects/${projectId}`)
    } catch (err) {
      console.error("Failed to create project:", err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
          >
            <div className="glass-card aurora-border w-full max-w-lg p-6">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-aurora flex items-center justify-center shadow-glow-purple">
                    <Sparkles size={14} className="text-white" />
                  </div>
                  <h2 className="font-semibold text-white">New Project</h2>
                </div>
                <button onClick={onClose} className="text-white/30 hover:text-white transition-colors">
                  <X size={18} />
                </button>
              </div>

              {/* Form */}
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-white/50 uppercase tracking-wider block mb-1.5">
                    Project Name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Todo App, E-commerce Store"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder:text-white/25 text-sm outline-none focus:border-violet-500/50 transition-colors"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-white/50 uppercase tracking-wider block mb-1.5">
                    What do you want to build?
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe your project in detail. Include features, target users, and any specific requirements..."
                    rows={4}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder:text-white/25 text-sm outline-none focus:border-violet-500/50 transition-colors resize-none"
                  />
                </div>

                {/* File attachment hint */}
                <div className="flex items-center gap-2 text-xs text-white/30">
                  <Paperclip size={12} />
                  <span>File attachments coming in v2.0</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 mt-6">
                <Button
                  variant="ghost"
                  onClick={onClose}
                  className="flex-1 text-white/50 hover:text-white"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!name || !description || loading}
                  className="flex-1 bg-aurora hover:opacity-90 text-white shadow-glow-purple disabled:opacity-40"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      Starting...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      Start Building
                      <ArrowRight size={14} />
                    </span>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

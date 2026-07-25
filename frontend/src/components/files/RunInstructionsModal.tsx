import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { X, Copy, CheckCircle2, Terminal } from "lucide-react"

interface RunInstructionsModalProps {
  projectId: string
  open: boolean
  onClose: () => void
}

interface InstructionStep {
  title: string
  commands?: string[]
  note?: string
}

interface InstructionsData {
  markdown?: string
  steps?: InstructionStep[]
}

export function RunInstructionsModal({
  projectId, open, onClose
}: RunInstructionsModalProps) {
  const [instructions, setInstructions] = useState<InstructionsData | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  useEffect(() => {
    if (open && projectId) {
      fetch(`/api/projects/${projectId}/run-instructions`)
        .then((r) => r.json())
        .then((data) => {
          if (data.markdown && !data.steps) {
            // Parse markdown code blocks into step commands for easy copy
            const parsedSteps: InstructionStep[] = []
            const lines = data.markdown.split("\n")
            let currentTitle = "Setup & Run Instructions"
            let currentCommands: string[] = []

            for (const line of lines) {
              if (line.startsWith("## ") || line.startsWith("### ")) {
                if (currentCommands.length > 0) {
                  parsedSteps.push({ title: currentTitle, commands: currentCommands })
                  currentCommands = []
                }
                currentTitle = line.replace(/^#+\s*/, "")
              } else if (line.startsWith("```") && !line.endsWith("```")) {
                // code block start/end
                continue
              } else if (line.trim() && !line.startsWith("#")) {
                if (line.includes("cd ") || line.includes("pip ") || line.includes("npm ") || line.includes("python ") || line.includes("uvicorn ")) {
                  currentCommands.push(line.trim())
                }
              }
            }
            if (currentCommands.length > 0) {
              parsedSteps.push({ title: currentTitle, commands: currentCommands })
            }

            setInstructions({ markdown: data.markdown, steps: parsedSteps.length > 0 ? parsedSteps : undefined })
          } else {
            setInstructions(data)
          }
        })
        .catch(() => setInstructions(null))
    }
  }, [open, projectId])

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 16 }}
            transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
            className="fixed inset-0 flex items-center justify-center z-50 p-4"
          >
            <div className="glass-card aurora-border w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto bg-slate-900/90 shadow-2xl border border-white/10 rounded-2xl">
              {/* Header */}
              <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <Terminal size={20} className="text-emerald-400" />
                  <h2 className="font-semibold text-white text-base">
                    How to Run Project
                  </h2>
                </div>
                <button
                  onClick={onClose}
                  className="text-white/40 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5 cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {!instructions ? (
                <div className="text-center py-8">
                  <div className="w-6 h-6 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto" />
                  <p className="text-xs text-white/40 mt-3">Loading instructions...</p>
                </div>
              ) : instructions.steps && instructions.steps.length > 0 ? (
                <div className="space-y-4">
                  {instructions.steps.map((step, i) => (
                    <div key={i} className="glass-card p-4 rounded-xl border border-white/10 bg-slate-950/60">
                      <p className="text-xs text-white/40 uppercase tracking-wider mb-3 font-semibold">
                        {step.title}
                      </p>
                      {step.commands?.map((cmd, j) => (
                        <div
                          key={j}
                          className="glass-card p-3 rounded-lg flex items-center gap-2 mb-2 bg-slate-900/80 border border-white/5"
                        >
                          <code className="text-xs text-emerald-300 font-mono flex-1 overflow-x-auto">
                            {cmd}
                          </code>
                          <button
                            onClick={() => copyToClipboard(cmd, `${i}-${j}`)}
                            className="text-white/40 hover:text-white transition-colors flex-shrink-0 cursor-pointer p-1"
                            title="Copy command"
                          >
                            {copied === `${i}-${j}` ? (
                              <CheckCircle2 size={14} className="text-emerald-400" />
                            ) : (
                              <Copy size={14} />
                            )}
                          </button>
                        </div>
                      ))}
                      {step.note && (
                        <p className="text-xs text-white/40 mt-2 italic">{step.note}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-950/60">
                  <pre className="text-xs text-white/80 font-mono whitespace-pre-wrap leading-relaxed overflow-auto max-h-[50vh]">
                    {instructions.markdown}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

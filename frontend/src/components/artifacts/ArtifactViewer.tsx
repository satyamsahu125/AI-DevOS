import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  FileText, Code2, Shield, Palette,
  Cpu, TestTube, BookOpen, Rocket,
  RotateCcw, ChevronDown,
  CheckCircle2, XCircle
} from "lucide-react"

interface StageMetaItem {
  label: string
  icon: any
  color: string
}

const STAGE_META: Record<string, StageMetaItem> = {
  strategic_review: { label: "Strategic Review", icon: Cpu, color: "violet" },
  StrategicReview: { label: "Strategic Review", icon: Cpu, color: "violet" },
  product_owner: { label: "Requirements", icon: FileText, color: "blue" },
  ProductOwner: { label: "Requirements", icon: FileText, color: "blue" },
  architect: { label: "Architecture", icon: Code2, color: "cyan" },
  Architect: { label: "Architecture", icon: Code2, color: "cyan" },
  designer: { label: "Design", icon: Palette, color: "pink" },
  Designer: { label: "Design", icon: Palette, color: "pink" },
  security: { label: "Security", icon: Shield, color: "red" },
  Security: { label: "Security", icon: Shield, color: "red" },
  sprint_planner: { label: "Sprint Plan", icon: RotateCcw, color: "amber" },
  SprintPlanner: { label: "Sprint Plan", icon: RotateCcw, color: "amber" },
  scrum_master: { label: "Scrum Plan", icon: RotateCcw, color: "orange" },
  ScrumMaster: { label: "Scrum Plan", icon: RotateCcw, color: "orange" },
  file_planner: { label: "File Structure", icon: Code2, color: "teal" },
  FileStructurePlanner: { label: "File Structure", icon: Code2, color: "teal" },
  backend: { label: "Backend Code", icon: Code2, color: "emerald" },
  BackendDeveloper: { label: "Backend Code", icon: Code2, color: "emerald" },
  frontend: { label: "Frontend Code", icon: Code2, color: "green" },
  FrontendDeveloper: { label: "Frontend Code", icon: Code2, color: "green" },
  qa: { label: "QA Report", icon: TestTube, color: "yellow" },
  QA: { label: "QA Report", icon: TestTube, color: "yellow" },
  document: { label: "Documentation", icon: BookOpen, color: "indigo" },
  Document: { label: "Documentation", icon: BookOpen, color: "indigo" },
  devops: { label: "DevOps", icon: Rocket, color: "purple" },
  DevOps: { label: "DevOps", icon: Rocket, color: "purple" },
  retro: { label: "Retrospective", icon: RotateCcw, color: "gray" },
  Retro: { label: "Retrospective", icon: RotateCcw, color: "gray" },
}

interface ArtifactViewerProps {
  projectId: string
  stagesCompleted?: string[]
}

export function ArtifactViewer({ projectId, stagesCompleted = [] }: ArtifactViewerProps) {
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [artifact, setArtifact] = useState<any>(null)
  const [history, setHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    if (stagesCompleted.length > 0 && !selectedStage) {
      setSelectedStage(stagesCompleted[stagesCompleted.length - 1])
    }
  }, [stagesCompleted, selectedStage])

  useEffect(() => {
    if (selectedStage && projectId) {
      loadArtifact(selectedStage)
    }
  }, [selectedStage, projectId])

  const loadArtifact = async (stage: string) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/artifacts/${projectId}/${stage}`)
      if (res.ok) {
        const data = await res.json()
        setArtifact(data)
      } else {
        setArtifact(null)
      }

      const histRes = await fetch(`/api/artifacts/${projectId}/${stage}/history`)
      if (histRes.ok) {
        const histData = await histRes.json()
        setHistory(histData.attempts || [])
      } else {
        setHistory([])
      }
    } catch {
      setArtifact(null)
      setHistory([])
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-full bg-slate-950/60">
      {/* Stage selector tabs */}
      <div className="flex overflow-x-auto gap-1.5 p-3 border-b border-white/10 scrollbar-none bg-slate-900/60">
        {stagesCompleted.map((stage) => {
          const meta = STAGE_META[stage] || {
            label: stage,
            icon: FileText,
            color: "white",
          }
          const Icon = meta.icon
          const active = selectedStage === stage
          return (
            <button
              key={stage}
              onClick={() => setSelectedStage(stage)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition-all duration-200 flex-shrink-0 cursor-pointer ${
                active
                  ? "bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 shadow-sm"
                  : "text-white/40 hover:text-white/70 hover:bg-white/5"
              }`}
            >
              <Icon size={12} />
              {meta.label}
              <CheckCircle2 size={10} className="text-emerald-400 ml-0.5" />
            </button>
          )
        })}
      </div>

      {/* Artifact content */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-white/5 animate-pulse rounded-lg border border-white/5" />
            ))}
          </div>
        ) : artifact ? (
          <motion.div
            key={selectedStage}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            {/* Artifact header */}
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-white/5">
              <div>
                <h3 className="text-sm font-semibold text-white/90">
                  {STAGE_META[selectedStage || ""]?.label || selectedStage}
                </h3>
                <p className="text-xs text-white/40 mt-0.5">
                  Approved on attempt {artifact.approved_attempt || 1}
                  {artifact.created_at && (
                    <span className="ml-2">
                      · {new Date(artifact.created_at).toLocaleTimeString()}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {history.length > 1 && (
                  <button
                    onClick={() => setShowHistory(!showHistory)}
                    className="text-xs text-white/40 hover:text-white/70 flex items-center gap-1 transition-colors px-2 py-1 rounded bg-white/5 hover:bg-white/10"
                  >
                    {history.length} attempts
                    <ChevronDown
                      size={12}
                      className={`transition-transform duration-200 ${showHistory ? "rotate-180" : ""}`}
                    />
                  </button>
                )}
              </div>
            </div>

            {/* Attempt history */}
            <AnimatePresence>
              {showHistory && history.length > 1 && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="mb-4 overflow-hidden"
                >
                  <div className="glass-card p-3 space-y-2 rounded-xl border border-white/10 bg-slate-900/40">
                    <p className="text-xs text-white/40 font-medium mb-1">Attempt history</p>
                    {history.map((attempt, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        {attempt.approved ? (
                          <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />
                        ) : (
                          <XCircle size={12} className="text-rose-400 shrink-0" />
                        )}
                        <span className="text-white/60 font-mono">
                          Attempt {attempt.attempt_number || i + 1}
                        </span>
                        {attempt.reviewer_feedback && (
                          <span className="text-white/40 truncate">— {attempt.reviewer_feedback.slice(0, 60)}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Structured content if available */}
            {artifact.structured_content &&
            Object.keys(artifact.structured_content).length > 0 ? (
              <StructuredArtifactView
                stage={selectedStage || ""}
                data={artifact.structured_content}
              />
            ) : (
              /* Raw markdown fallback */
              <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
                <pre className="text-xs text-white/80 whitespace-pre-wrap font-mono leading-relaxed overflow-auto max-h-[60vh]">
                  {artifact.content}
                </pre>
              </div>
            )}
          </motion.div>
        ) : (
          <div className="flex flex-col items-center justify-center h-40 text-center">
            <FileText size={28} className="text-white/15 mb-3" />
            <p className="text-sm text-white/40">
              Complete stages to view their artifacts
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function StructuredArtifactView({ stage, data }: { stage: string; data: any }) {
  const normStage = stage.toLowerCase().replace(/_/g, "")

  if (normStage === "productowner" || normStage === "requirements") {
    return <RequirementsView data={data} />
  }
  if (normStage === "architect" || normStage === "architecture") {
    return <ArchitectureView data={data} />
  }
  if (normStage === "security") {
    return <SecurityView data={data} />
  }
  if (normStage === "sprintplanner" || normStage === "sprintplan") {
    return <SprintView data={data} />
  }

  /* Default: formatted JSON */
  return (
    <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
      <pre className="text-xs text-white/80 whitespace-pre-wrap font-mono overflow-auto max-h-[60vh]">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

function RequirementsView({ data }: { data: any }) {
  return (
    <div className="space-y-4">
      {data.project_name && (
        <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <h4 className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-1">
            Project
          </h4>
          <p className="text-white/90 font-medium">{data.project_name}</p>
          {data.tagline && <p className="text-white/50 text-sm mt-1">{data.tagline}</p>}
        </div>
      )}
      {data.requirements?.map((req: any, i: number) => (
        <div key={i} className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-mono text-violet-400 font-semibold">{req.req_id}</span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                req.priority === "MUST"
                  ? "bg-rose-500/15 text-rose-400 border border-rose-500/20"
                  : req.priority === "SHOULD"
                  ? "bg-amber-500/15 text-amber-400 border border-amber-500/20"
                  : "bg-white/5 text-white/40 border border-white/10"
              }`}
            >
              {req.priority}
            </span>
            <span className="text-xs text-white/40 ml-auto">{req.category}</span>
          </div>
          <p className="text-sm text-white/80 leading-relaxed">{req.description}</p>
          {req.edge_cases?.length > 0 && (
            <div className="mt-2.5 pt-2 border-t border-white/5">
              <p className="text-xs text-white/40 mb-1 font-medium">Edge cases:</p>
              {req.edge_cases.map((ec: string, j: number) => (
                <p key={j} className="text-xs text-white/60 ml-2 py-0.5">
                  · {ec}
                </p>
              ))}
            </div>
          )}
        </div>
      ))}
      {data.out_of_scope?.length > 0 && (
        <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <h4 className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">
            Out of Scope
          </h4>
          {data.out_of_scope.map((item: string, i: number) => (
            <p key={i} className="text-sm text-white/50 flex items-center gap-2 py-1">
              <XCircle size={14} className="text-rose-400/60 shrink-0" />
              {item}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function ArchitectureView({ data }: { data: any }) {
  return (
    <div className="space-y-4">
      {data.tech_stack && (
        <div className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <h4 className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3">
            Tech Stack
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(data.tech_stack).map(([k, v]) => (
              <div key={k} className="text-sm">
                <span className="text-white/40">{k}: </span>
                <span className="text-cyan-300 font-medium">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {data.modules?.map((mod: any, i: number) => (
        <div key={i} className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-medium text-white/90">{mod.name}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-white/5 text-white/40 font-mono">
              {mod.layer}
            </span>
          </div>
          <p className="text-xs text-white/60 leading-relaxed">{mod.purpose}</p>
          {mod.dependencies?.length > 0 && (
            <p className="text-xs text-white/40 mt-2 pt-2 border-t border-white/5">
              Depends on: <span className="text-cyan-400/70">{mod.dependencies.join(", ")}</span>
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

function SecurityView({ data }: { data: any }) {
  const findings = data.findings || []
  return (
    <div className="space-y-3">
      {findings.map((f: any, i: number) => (
        <div
          key={i}
          className={`glass-card p-4 rounded-xl border-l-2 ${
            f.severity === "CRITICAL"
              ? "border-rose-500 bg-rose-500/5"
              : f.severity === "HIGH"
              ? "border-amber-500 bg-amber-500/5"
              : "border-white/20 bg-slate-900/40"
          }`}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded ${
                f.severity === "CRITICAL"
                  ? "bg-rose-500/20 text-rose-400"
                  : f.severity === "HIGH"
                  ? "bg-amber-500/20 text-amber-400"
                  : "bg-white/10 text-white/60"
              }`}
            >
              {f.severity}
            </span>
            <span className="text-sm font-medium text-white/90">{f.title || f.type}</span>
          </div>
          <p className="text-xs text-white/60 leading-relaxed mt-1">{f.description}</p>
          {f.recommendation && (
            <p className="text-xs text-emerald-400/80 mt-2 pt-2 border-t border-white/5">
              Fix: {f.recommendation}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

function SprintView({ data }: { data: any }) {
  return (
    <div className="space-y-4">
      {data.sprints?.map((sprint: any, i: number) => (
        <div key={i} className="glass-card p-4 rounded-xl border border-white/10 bg-slate-900/40">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs bg-violet-500/20 text-violet-300 border border-violet-500/30 px-2 py-0.5 rounded font-mono">
              Sprint {sprint.sprint_number}
            </span>
            <span className="text-sm font-medium text-white/90">{sprint.name}</span>
          </div>
          <p className="text-xs text-white/60 mb-3">{sprint.goal}</p>
          <div className="flex flex-wrap gap-1.5">
            {sprint.features?.map((f: string, j: number) => (
              <span
                key={j}
                className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-white/60 border border-white/5"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

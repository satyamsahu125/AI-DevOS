import { STAGES, STAGE_LABELS, type StageName } from "../../lib/api"

const STAGE_ICONS: Record<StageName, string> = {
  StrategicReview:     "🎯",
  ProductOwner:        "📋",
  Architect:           "🏛",
  Designer:            "🎨",
  Security:            "🔒",
  FileStructurePlanner:"📁",
  BackendDeveloper:    "⚙",
  FrontendDeveloper:   "🖥",
  QA:                  "🧪",
  Document:            "📄",
  DevOps:              "🚀",
  Retro:               "🔄",
}

interface StageRailProps {
  completedStages: string[]
  currentStage: string | null
  failedStage: string | null
}

export function StageRail({ completedStages, currentStage, failedStage }: StageRailProps) {
  const completed = new Set(completedStages.map(s => s.toLowerCase()))

  return (
    <div className="flex items-center gap-0 overflow-x-auto scrollbar-none">
      {STAGES.map((stage, i) => {
        const key = stage.toLowerCase()
        const isCurrent = currentStage?.toLowerCase() === key
        const isDone = completed.has(key)
        const isFailed = failedStage?.toLowerCase() === key

        const dot =
          isFailed  ? "bg-rose-500 ring-rose-500/30" :
          isDone    ? "bg-emerald-500 ring-emerald-500/20" :
          isCurrent ? "bg-indigo-500 ring-indigo-500/30 animate-pulse" :
                      "bg-zinc-700"

        const text =
          isFailed  ? "text-rose-400" :
          isDone    ? "text-emerald-400" :
          isCurrent ? "text-indigo-300 font-medium" :
                      "text-zinc-600"

        return (
          <div key={stage} className="flex items-center">
            {/* Stage node */}
            <div className="flex flex-col items-center gap-1 px-2">
              <div className={`flex h-6 w-6 items-center justify-center rounded-full ring-2 ${dot} text-[10px]`} title={STAGE_LABELS[stage]}>
                {isFailed ? "✗" : isDone ? "✓" : isCurrent ? STAGE_ICONS[stage] : String(i + 1)}
              </div>
              <span className={`whitespace-nowrap text-[9px] leading-none ${text}`}>
                {STAGE_LABELS[stage]}
              </span>
            </div>

            {/* Connector */}
            {i < STAGES.length - 1 && (
              <div className={`h-px w-3 shrink-0 ${isDone ? "bg-emerald-600" : "bg-zinc-800"}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

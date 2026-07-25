import { Sparkles, Activity, FileText, Code2 } from "lucide-react"

export function ContextPanel() {
  return (
    <div className="h-full w-[380px] bg-surface-2/90 backdrop-blur-glass p-5 flex flex-col gap-4 text-white">
      <div className="flex items-center gap-2 border-b border-white/10 pb-3">
        <Sparkles size={16} className="text-violet-400" />
        <h3 className="font-semibold text-sm">Active Workspace Context</h3>
      </div>
      <div className="space-y-3 flex-1 overflow-y-auto">
        <div className="glass-card p-3">
          <div className="flex items-center gap-2 text-xs text-violet-300 font-medium mb-1">
            <Activity size={12} />
            <span>Workflow Status</span>
          </div>
          <p className="text-xs text-white/60">AI DevOS Studio active and monitoring execution trajectory.</p>
        </div>

        <div className="glass-card p-3">
          <div className="flex items-center gap-2 text-xs text-cyan-300 font-medium mb-1">
            <Code2 size={12} />
            <span>Generated Code</span>
          </div>
          <p className="text-xs text-white/60">Frontend and Backend source code ready in workspace artifacts.</p>
        </div>

        <div className="glass-card p-3">
          <div className="flex items-center gap-2 text-xs text-emerald-300 font-medium mb-1">
            <FileText size={12} />
            <span>Specifications</span>
          </div>
          <p className="text-xs text-white/60">Approved architecture and design specifications attached.</p>
        </div>
      </div>
    </div>
  )
}

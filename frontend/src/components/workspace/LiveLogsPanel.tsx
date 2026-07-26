import { useEffect, useRef } from "react"
import { motion } from "framer-motion"

const LOG_COLORS: Record<string, string> = {
  "✓": "text-emerald-400",
  "✗": "text-rose-400",
  "↩": "text-amber-400",
  "▶": "text-violet-400",
  "📄": "text-cyan-400",
  "❓": "text-blue-400",
  "⏸": "text-amber-400",
  "🎉": "text-yellow-400",
  "🔍": "text-violet-400",
}

function getLogColor(line: string): string {
  for (const [icon, color] of Object.entries(LOG_COLORS)) {
    if (line.startsWith(icon)) return color
  }
  return "text-white/50"
}

export function LiveLogsPanel({ logs }: { logs: string[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length])

  return (
    <div className="h-full overflow-y-auto p-3 font-mono text-xs space-y-0.5">
      {logs.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <p className="text-white/20">
            Pipeline logs will appear here in real time
          </p>
        </div>
      ) : (
        logs.map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.15 }}
            className={`leading-relaxed ${getLogColor(line)}`}
          >
            {line}
          </motion.div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  )
}

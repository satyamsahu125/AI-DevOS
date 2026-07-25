import { motion, AnimatePresence } from "framer-motion"
import { useState } from "react"
import { SlimNav } from "./SlimNav"
import { ContextPanel } from "./ContextPanel"

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [contextOpen, setContextOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-[#0A0A14] text-white">
      {/* Left: Icon-only nav — 60px */}
      <SlimNav onOpenContext={() => setContextOpen(!contextOpen)} />

      {/* Center: Main area */}
      <main className="flex-1 overflow-hidden relative z-10">
        <AnimatePresence mode="wait">
          <motion.div
            key="content"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
            className="h-full"
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Right: Context panel — slides in */}
      <AnimatePresence>
        {contextOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 380, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="overflow-hidden border-l border-white/10 shrink-0"
          >
            <ContextPanel />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

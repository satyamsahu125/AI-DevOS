import { motion } from "framer-motion"
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip"
import { useNavigate, useLocation } from "react-router-dom"
import {
  Home, FolderOpen, Bot, Brain,
  Settings, Plus, Sparkles
} from "lucide-react"

const navItems = [
  { icon: Home,       label: "Home",        href: "/"           },
  { icon: FolderOpen, label: "Projects",    href: "/projects"   },
  { icon: Bot,        label: "Agents",      href: "/agents"     },
  { icon: Brain,      label: "Memory",      href: "/memory"     },
]

interface SlimNavProps {
  onOpenContext?: () => void
}

export function SlimNav({ onOpenContext }: SlimNavProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const pathname = location.pathname

  return (
    <TooltipProvider delayDuration={150}>
      <nav className="w-[60px] h-screen flex flex-col items-center py-4 border-r border-white/10 bg-black/20 backdrop-blur-glass z-20 shrink-0">
        {/* Logo */}
        <motion.div
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          className="w-9 h-9 rounded-xl bg-aurora flex items-center justify-center cursor-pointer shadow-glow-purple mb-6"
          onClick={() => navigate("/")}
        >
          <Sparkles size={16} className="text-white" />
        </motion.div>

        {/* New Project button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => navigate("/projects/new")}
              className="w-9 h-9 rounded-lg border border-dashed border-white/20 flex items-center justify-center hover:border-violet-500 hover:bg-violet-500/10 transition-all duration-200 mb-4"
            >
              <Plus size={16} className="text-white/50 hover:text-violet-400" />
            </motion.button>
          </TooltipTrigger>
          <TooltipContent side="right">New Project</TooltipContent>
        </Tooltip>

        <div className="w-8 border-t border-white/10 mb-4" />

        {/* Nav items */}
        <div className="flex flex-col gap-2 flex-1">
          {navItems.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href))
            const Icon = item.icon

            return (
              <Tooltip key={item.href}>
                <TooltipTrigger asChild>
                  <motion.button
                    whileHover={{ scale: 1.08, x: 2 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => navigate(item.href)}
                    className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-200 relative group ${
                      active
                        ? "bg-violet-600/20 text-violet-400 shadow-glow-purple"
                        : "text-white/40 hover:text-white/80 hover:bg-white/5"
                    }`}
                  >
                    {active && (
                      <motion.div
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-lg bg-violet-600/20 border border-violet-500/30"
                        transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
                      />
                    )}
                    <Icon size={16} className="relative z-10" />
                  </motion.button>
                </TooltipTrigger>
                <TooltipContent side="right">{item.label}</TooltipContent>
              </Tooltip>
            )
          })}
        </div>

        {/* Bottom: settings + avatar */}
        <div className="flex flex-col items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <motion.button
                whileHover={{ scale: 1.08 }}
                onClick={() => navigate("/settings")}
                className="w-9 h-9 rounded-lg flex items-center justify-center text-white/40 hover:text-white/80 hover:bg-white/5 transition-all duration-200"
              >
                <Settings size={16} />
              </motion.button>
            </TooltipTrigger>
            <TooltipContent side="right">Settings</TooltipContent>
          </Tooltip>

          {/* User avatar */}
          <div
            onClick={onOpenContext}
            className="w-8 h-8 rounded-full bg-aurora-subtle border border-violet-500/30 flex items-center justify-center text-xs font-bold text-violet-300 cursor-pointer hover:border-violet-400 transition-all"
          >
            AI
          </div>
        </div>
      </nav>
    </TooltipProvider>
  )
}

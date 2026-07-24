import { useState } from "react"
import { NavLink, useParams } from "react-router-dom"
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  Gauge,
  GitBranch,
  Layers,
  ScrollText,
  Settings,
  Sparkles,
  Workflow,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { useWorkflowStatus } from "@/hooks/useWorkflowStatus"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const COLLAPSE_KEY = "aidevos:sidebar-collapsed"

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/memory", label: "Memory", icon: Layers },
  { to: "/settings", label: "Settings", icon: Settings },
]

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  complete: "success",
  running: "warning",
  failed: "destructive",
  not_started: "muted",
  paused: "muted",
  stopped: "muted",
}

export function Sidebar() {
  const { projectId } = useParams()
  const { status } = useWorkflowStatus(projectId ?? null, 4000)
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem(COLLAPSE_KEY) === "1")

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0")
      return next
    })
  }

  return (
    <aside
      className={cn(
        "relative flex h-screen shrink-0 flex-col border-r border-border bg-card/40 transition-[width]",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className={cn("flex items-center gap-2 px-5 py-5", collapsed && "justify-center px-0")}>
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Sparkles className="size-4" />
        </div>
        {!collapsed && (
          <div>
            <p className="text-sm font-semibold leading-none">AI DevOS</p>
            <p className="text-[11px] text-muted-foreground">Engineering Workspace</p>
          </div>
        )}
      </div>

      <nav className={cn("flex flex-col gap-0.5", collapsed ? "items-center px-2" : "px-3")}>
        {NAV_ITEMS.map((item) =>
          collapsed ? (
            <Tooltip key={item.to}>
              <TooltipTrigger asChild>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      "flex size-9 items-center justify-center rounded-md transition-colors",
                      isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )
                  }
                >
                  <item.icon className="size-4" />
                </NavLink>
              </TooltipTrigger>
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          ) : (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ),
        )}
      </nav>

      <div className="mt-auto border-t border-border p-4">
        {collapsed ? null : projectId ? (
          <div className="flex flex-col gap-2 rounded-lg border border-border bg-background/60 p-3">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
              <GitBranch className="size-3" />
              Current Project
            </div>
            <p className="truncate text-xs font-mono text-foreground/80" title={projectId}>
              {projectId.slice(0, 8)}&hellip;
            </p>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Workflow className="size-3" />
                {status?.current_stage ?? "--"}
              </span>
              <Badge variant={STATUS_VARIANT[status?.status ?? "not_started"]}>{status?.status ?? "unknown"}</Badge>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-border p-3 text-[11px] text-muted-foreground">
            <ScrollText className="size-3.5" />
            No project open
          </div>
        )}
      </div>

      <button
        onClick={toggleCollapsed}
        className="absolute -right-3 top-16 flex size-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm hover:text-foreground"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronLeft className="size-3.5" />}
      </button>
    </aside>
  )
}

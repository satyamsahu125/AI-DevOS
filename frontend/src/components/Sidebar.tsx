import { useState, useEffect, useMemo } from "react"
import { NavLink, useNavigate, useParams } from "react-router-dom"
import { motion } from "framer-motion"
import {
  Plus,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  MessageSquare,
  Bot,
  Layers,
  Settings,
  FolderKanban,
  Trash2,
  Cpu,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { api, type ProjectSummary, type ReadyStatus } from "@/lib/api"
import { NewProjectDialog } from "@/components/NewProjectDialog"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const COLLAPSE_KEY = "aidevos:sidebar-collapsed"

function groupProjectsByDate(projects: ProjectSummary[] | null) {
  if (!projects || projects.length === 0) return { today: [], yesterday: [], earlier: [] }
  const now = new Date()
  const todayStr = now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = yesterday.toDateString()

  const today: ProjectSummary[] = []
  const yesterdayGroup: ProjectSummary[] = []
  const earlier: ProjectSummary[] = []

  projects.forEach((p) => {
    const d = new Date(p.created_at).toDateString()
    if (d === todayStr) {
      today.push(p)
    } else if (d === yesterdayStr) {
      yesterdayGroup.push(p)
    } else {
      earlier.push(p)
    }
  })

  return { today, yesterday: yesterdayGroup, earlier }
}

export function Sidebar() {
  const { projectId } = useParams<{ projectId?: string }>()
  const navigate = useNavigate()

  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem(COLLAPSE_KEY) === "1")
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [ready, setReady] = useState<ReadyStatus | null>(null)
  const [newProjectOpen, setNewProjectOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchActive, setSearchActive] = useState(false)

  function loadProjects() {
    api.listProjects().then(setProjects).catch(() => setProjects([]))
  }

  useEffect(() => {
    loadProjects()
    api.ready().then(setReady).catch(() => setReady(null))
  }, [projectId])

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev
      window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0")
      return next
    })
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (confirm("Delete this project chat workspace?")) {
      await api.deleteProject(id)
      loadProjects()
      if (projectId === id) {
        navigate("/")
      }
    }
  }

  const filteredProjects = useMemo(() => {
    if (!projects) return []
    if (!searchQuery.trim()) return projects
    return projects.filter((p) => p.name.toLowerCase().includes(searchQuery.toLowerCase()))
  }, [projects, searchQuery])

  const grouped = useMemo(() => groupProjectsByDate(filteredProjects), [filteredProjects])

  return (
    <>
      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 68 : 280 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="relative flex h-screen shrink-0 flex-col border-r border-zinc-800/80 bg-zinc-950 text-zinc-200 z-30 select-none"
      >
        {/* Top Action Bar */}
        <div className="flex flex-col gap-2 p-3 border-b border-zinc-800/40">
          <div className="flex items-center justify-between">
            <button
              onClick={toggleCollapsed}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 rounded-lg transition-colors"
              title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            >
              {collapsed ? <PanelLeftOpen className="size-5" /> : <PanelLeftClose className="size-5" />}
            </button>

            {!collapsed && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setSearchActive((prev) => !prev)}
                  className={cn(
                    "p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 rounded-lg transition-colors",
                    searchActive && "text-zinc-100 bg-zinc-800",
                  )}
                  title="Search recents"
                >
                  <Search className="size-4" />
                </button>
              </div>
            )}
          </div>

          {/* Search Box */}
          {!collapsed && searchActive && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
              <input
                type="text"
                placeholder="Search projects..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl bg-zinc-900 border border-zinc-800 px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-700"
              />
            </motion.div>
          )}

          {/* Prominent "+ New chat" Button */}
          <button
            onClick={() => setNewProjectOpen(true)}
            className={cn(
              "flex items-center justify-center gap-2.5 rounded-2xl bg-zinc-100 text-zinc-950 font-medium py-2.5 px-4 shadow-sm hover:bg-white transition-all active:scale-[0.98]",
              collapsed ? "w-10 h-10 px-0" : "w-full text-xs font-semibold",
            )}
            title="New Chat / Project"
          >
            <Plus className="size-4 shrink-0" />
            {!collapsed && <span>New chat</span>}
          </button>
        </div>

        {/* Middle Recents List */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
          {!collapsed ? (
            <>
              {grouped.today.length > 0 && (
                <div>
                  <p className="px-3 py-1 text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Today</p>
                  <div className="space-y-0.5 mt-1">
                    {grouped.today.map((item) => (
                      <ChatItem
                        key={item.project_id}
                        item={item}
                        activeId={projectId}
                        onSelect={(id) => navigate(`/projects/${id}`)}
                        onDelete={handleDelete}
                      />
                    ))}
                  </div>
                </div>
              )}

              {grouped.yesterday.length > 0 && (
                <div>
                  <p className="px-3 py-1 text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Yesterday</p>
                  <div className="space-y-0.5 mt-1">
                    {grouped.yesterday.map((item) => (
                      <ChatItem
                        key={item.project_id}
                        item={item}
                        activeId={projectId}
                        onSelect={(id) => navigate(`/projects/${id}`)}
                        onDelete={handleDelete}
                      />
                    ))}
                  </div>
                </div>
              )}

              {grouped.earlier.length > 0 && (
                <div>
                  <p className="px-3 py-1 text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Previous 7 Days</p>
                  <div className="space-y-0.5 mt-1">
                    {grouped.earlier.map((item) => (
                      <ChatItem
                        key={item.project_id}
                        item={item}
                        activeId={projectId}
                        onSelect={(id) => navigate(`/projects/${id}`)}
                        onDelete={handleDelete}
                      />
                    ))}
                  </div>
                </div>
              )}

              {filteredProjects.length === 0 && (
                <div className="p-4 text-center text-xs text-zinc-500">
                  <p>No recent chats</p>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center gap-2">
              {filteredProjects.slice(0, 8).map((item) => (
                <Tooltip key={item.project_id}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => navigate(`/projects/${item.project_id}`)}
                      className={cn(
                        "flex size-9 items-center justify-center rounded-xl transition-colors",
                        projectId === item.project_id ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                      )}
                    >
                      <MessageSquare className="size-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">{item.name}</TooltipContent>
                </Tooltip>
              ))}
            </div>
          )}
        </div>

        {/* Bottom Area: Workspace Nav, Model Info, User Profile */}
        <div className="border-t border-zinc-800/60 p-2 space-y-1">
          {!collapsed ? (
            <>
              {/* Workspace Quick Links */}
              <div className="space-y-0.5 mb-2 border-b border-zinc-800/40 pb-2">
                <NavLink
                  to="/projects"
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors",
                      isActive ? "bg-zinc-800/90 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )
                  }
                >
                  <FolderKanban className="size-3.5" /> Projects & Code
                </NavLink>
                <NavLink
                  to="/agents"
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors",
                      isActive ? "bg-zinc-800/90 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )
                  }
                >
                  <Bot className="size-3.5" /> Agent Roster
                </NavLink>
                <NavLink
                  to="/memory"
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors",
                      isActive ? "bg-zinc-800/90 text-white font-semibold" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )
                  }
                >
                  <Layers className="size-3.5" /> Memory
                </NavLink>
              </div>

              {/* Model Pill */}
              {ready && (
                <div className="flex items-center justify-between rounded-xl bg-zinc-900/80 px-3 py-2 border border-zinc-800/60 mb-2">
                  <div className="flex items-center gap-2 truncate">
                    <Cpu className="size-3.5 text-indigo-400 shrink-0" />
                    <span className="truncate text-[11px] font-mono text-zinc-300">{ready.model}</span>
                  </div>
                  <span className="size-2 rounded-full bg-emerald-400 shrink-0" />
                </div>
              )}

              {/* User Profile & Settings */}
              <div className="flex items-center justify-between rounded-xl p-2 hover:bg-zinc-900/80 transition-colors">
                <div className="flex items-center gap-2.5 truncate">
                  <div className="flex size-7 items-center justify-center rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 text-white text-xs font-bold">
                    AI
                  </div>
                  <div className="truncate">
                    <p className="text-xs font-semibold text-zinc-200 leading-tight">AI DevOS User</p>
                    <p className="text-[10px] text-zinc-500 truncate">Engineering Studio</p>
                  </div>
                </div>
                <NavLink to="/settings" className="p-1.5 text-zinc-400 hover:text-white rounded-lg transition-colors" title="Settings">
                  <Settings className="size-4" />
                </NavLink>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 py-1">
              <NavLink to="/settings" className="p-2 text-zinc-400 hover:text-white rounded-xl transition-colors" title="Settings">
                <Settings className="size-4" />
              </NavLink>
            </div>
          )}
        </div>
      </motion.aside>

      <NewProjectDialog
        open={newProjectOpen}
        onOpenChange={setNewProjectOpen}
        onCreated={(id) => navigate(`/projects/${id}`)}
      />
    </>
  )
}

function ChatItem({
  item,
  activeId,
  onSelect,
  onDelete,
}: {
  item: ProjectSummary
  activeId?: string
  onSelect: (id: string) => void
  onDelete: (e: React.MouseEvent, id: string) => void
}) {
  const isActive = activeId === item.project_id

  return (
    <div
      onClick={() => onSelect(item.project_id)}
      className={cn(
        "group relative flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium cursor-pointer transition-all",
        isActive ? "bg-zinc-800 text-white font-semibold shadow-sm" : "text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-200",
      )}
    >
      <div className="flex items-center gap-2.5 truncate min-w-0">
        <MessageSquare className={cn("size-3.5 shrink-0", isActive ? "text-indigo-400" : "text-zinc-500")} />
        <span className="truncate">{item.name}</span>
      </div>

      <button
        onClick={(e) => onDelete(e, item.project_id)}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-zinc-500 hover:text-rose-400 rounded"
        title="Delete"
      >
        <Trash2 className="size-3" />
      </button>
    </div>
  )
}

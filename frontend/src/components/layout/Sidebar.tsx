import { useNavigate, useLocation, useParams, useSearchParams } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { useAuth } from "../../lib/auth"

interface NavItem {
  icon: React.ReactNode
  label: string
  to?: string
  onClick?: () => void
  active?: boolean
  section?: string
}

function Icon({ d }: { d: string }) {
  return (
    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

const ICONS = {
  home:         "M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z M9 22V12h6v10",
  projects:     "M3 7h18M3 12h18M3 17h18",
  pipeline:     "M12 3v18M3 12h18",
  activity:     "M22 12h-4l-3 9L9 3l-3 9H2",
  artifacts:    "M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z",
  files:        "M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z M13 2v7h7",
  chat:         "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
  metrics:      "M18 20V10M12 20V4M6 20v-6",
  agents:       "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75",
  settings:     "M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z",
  help:         "M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3 M12 17h.01",
  collapse:     "M15 18l-6-6 6-6",
  analytics:    "M18 20V10M12 20V4M6 20v-6",
  admin:        "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75",
  integrations: "M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z M13 2v7h7",
  changes:      "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
  logout:       "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4 M16 17l5-5-5-5 M21 12H9",
}

// ── Sidebar widths ────────────────────────────────────────────────────────────
const SB_EXPANDED = 220
const SB_COLLAPSED = 52

interface SidebarProps {
  collapsed: boolean
  setCollapsed: (v: boolean) => void
  projectName?: string
  projectStatus?: string
}

export function Sidebar({ collapsed, setCollapsed, projectName, projectStatus }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const activeTab = searchParams.get("tab") ?? "activity"
  const { user, authEnabled, logout } = useAuth()

  const onProjectPage = projectId
    ? (location.pathname === `/projects/${projectId}` || location.pathname.startsWith(`/projects/${projectId}/`))
    : false

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + "/")

  const statusColor = projectStatus === "running" ? "#7C3AED"
    : projectStatus === "complete" ? "#10B981"
    : projectStatus === "failed"   ? "#F43F5E"
    : projectStatus === "paused"   ? "#F59E0B"
    : "rgba(233,233,237,.25)"

  function NavBtn({ icon, label, to, active, onClick }: NavItem) {
    const handleClick = () => { if (to) navigate(to); else onClick?.() }
    return (
      <motion.button
        onClick={handleClick}
        title={collapsed ? label : undefined}
        whileHover={{ backgroundColor: active ? undefined : "rgba(233,233,237,.05)" }}
        whileTap={{ scale: 0.97 }}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 10,
          padding: collapsed ? "9px 0" : "8px 10px",
          justifyContent: collapsed ? "center" : "flex-start",
          background: active ? "var(--color-accent-dim)" : "transparent",
          border: "none",
          borderLeft: active ? "2px solid var(--color-accent)" : "2px solid transparent",
          borderRadius: active ? "0 var(--radius-md) var(--radius-md) 0" : "0 var(--radius-md) var(--radius-md) 0",
          color: active ? "var(--color-accent)" : "rgba(233,233,237,.6)",
          cursor: "pointer", fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: active ? 500 : 400,
          whiteSpace: "nowrap", overflow: "hidden",
          marginLeft: collapsed ? 0 : -2,
          transition: "color 0.12s",
        }}
      >
        <span style={{ flexShrink: 0, display: "flex" }}>{icon}</span>
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              transition={{ duration: 0.18 }}
              style={{ overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {label}
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>
    )
  }

  function SectionLabel({ label }: { label: string }) {
    if (collapsed) return <div style={{ height: 1, background: "var(--color-divider)", margin: "8px 10px" }} />
    return (
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "rgba(233,233,237,.3)", padding: "12px 12px 4px" }}
        >
          {label}
        </motion.div>
      </AnimatePresence>
    )
  }

  async function handleLogout() {
    await logout()
    navigate("/")
  }

  const showUserSection = authEnabled && user && !user.anonymous

  return (
    <motion.aside
      animate={{ width: collapsed ? SB_COLLAPSED : SB_EXPANDED, minWidth: collapsed ? SB_COLLAPSED : SB_EXPANDED }}
      transition={{ type: "spring", stiffness: 320, damping: 34 }}
      style={{
        position: "relative", display: "flex", flexDirection: "column",
        background: "var(--color-surface)",
        borderRight: "1px solid var(--color-divider)",
        overflow: "hidden", zIndex: 10, flexShrink: 0,
      }}
    >

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "space-between", padding: collapsed ? "0" : "0 8px", height: 56, borderBottom: "1px solid var(--color-divider)", flexShrink: 0, gap: 4, overflow: "hidden" }}>
        {!collapsed && (
          <a href="/" style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--color-text)", textDecoration: "none", flex: 1, overflow: "hidden", minWidth: 0 }}>
            <span style={{ width: 28, height: 28, borderRadius: 7, background: "var(--color-accent)", display: "grid", placeItems: "center", flexShrink: 0 }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </span>
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.05 }}
              style={{ fontSize: 13.5, fontWeight: 700, letterSpacing: "-.025em", whiteSpace: "nowrap", overflow: "hidden" }}
            >
              AI DevOS
            </motion.span>
          </a>
        )}
        {collapsed && (
          <a href="/" style={{ width: 28, height: 28, borderRadius: 7, background: "var(--color-accent)", display: "grid", placeItems: "center" }}>
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </a>
        )}
        {!collapsed && (
          <motion.button
            onClick={() => setCollapsed(true)}
            title="Collapse sidebar"
            whileHover={{ backgroundColor: "var(--color-accent-dim)", borderColor: "var(--color-accent-border)", color: "var(--color-accent)" }}
            style={{ width: 28, height: 28, borderRadius: 7, border: "1px solid var(--color-divider)", background: "transparent", cursor: "pointer", display: "grid", placeItems: "center", color: "rgba(233,233,237,.4)", flexShrink: 0, transition: "background .12s, border-color .12s, color .12s" }}
          >
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M15 18l-6-6 6-6" /></svg>
          </motion.button>
        )}
        {collapsed && (
          <motion.button
            onClick={() => setCollapsed(false)}
            title="Expand sidebar"
            whileHover={{ color: "var(--color-accent)" }}
            style={{ position: "absolute", bottom: -1, right: -12, width: 20, height: 20, borderRadius: "0 6px 6px 0", border: "1px solid var(--color-divider)", borderLeft: "none", background: "var(--color-surface)", cursor: "pointer", display: "grid", placeItems: "center", color: "rgba(233,233,237,.4)", transition: "color .12s" }}
          >
            <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round"><path d="M9 18l6-6-6-6" /></svg>
          </motion.button>
        )}
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "8px 0", scrollbarWidth: "thin", scrollbarColor: "var(--color-divider) transparent" }}>

        <SectionLabel label="Navigate" />
        <NavBtn icon={<Icon d={ICONS.home} />}      label="Home"      to="/"          active={location.pathname === "/"} />
        <NavBtn icon={<Icon d={ICONS.projects} />}  label="Projects"  to="/projects"  active={location.pathname === "/projects"} />
        <NavBtn icon={<Icon d={ICONS.analytics} />} label="Analytics" to="/analytics" active={isActive("/analytics")} />
        {user?.role === "admin" && (
          <NavBtn icon={<Icon d={ICONS.admin} />} label="Admin" to="/admin" active={isActive("/admin")} />
        )}

        {projectId && (
          <>
            <SectionLabel label="Project" />
            <NavBtn icon={<Icon d={ICONS.activity} />}      label="Activity"     to={`/projects/${projectId}`}                    active={onProjectPage && activeTab === "activity"} />
            <NavBtn icon={<Icon d={ICONS.files} />}         label="Files"        to={`/projects/${projectId}?tab=files`}          active={onProjectPage && activeTab === "files"} />
            <NavBtn icon={<Icon d={ICONS.artifacts} />}     label="Artifacts"    to={`/projects/${projectId}?tab=artifacts`}      active={onProjectPage && activeTab === "artifacts"} />
            <NavBtn icon={<Icon d={ICONS.metrics} />}       label="Metrics"      to={`/projects/${projectId}?tab=metrics`}        active={onProjectPage && activeTab === "metrics"} />
            <NavBtn icon={<Icon d={ICONS.chat} />}          label="Chat"         to={`/projects/${projectId}?tab=chat`}           active={onProjectPage && activeTab === "chat"} />
            <NavBtn icon={<Icon d={ICONS.integrations} />}  label="Integrations" to={`/projects/${projectId}?tab=integrations`}  active={onProjectPage && activeTab === "integrations"} />
            <NavBtn icon={<Icon d={ICONS.changes} />}       label="Changes"      to={`/projects/${projectId}?tab=changes`}       active={onProjectPage && activeTab === "changes"} />
          </>
        )}

        <SectionLabel label="System" />
        <NavBtn icon={<Icon d={ICONS.agents} />}   label="Agents"   to="/projects" active={false} />
        <NavBtn icon={<Icon d={ICONS.settings} />} label="Settings" to="/settings" active={isActive("/settings")} />
        <NavBtn icon={<Icon d={ICONS.help} />}     label="Help"     to="/" active={false} />
      </div>

      {/* Footer — project status */}
      {projectId && projectName && (
        <div style={{ borderTop: "1px solid var(--color-divider)", padding: collapsed ? "12px 0" : "10px 12px", display: "flex", alignItems: "center", gap: 8, justifyContent: collapsed ? "center" : "flex-start", flexShrink: 0, overflow: "hidden" }}>
          <motion.span
            animate={{ opacity: [0.6, 1, 0.6] }}
            transition={projectStatus === "running" ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : {}}
            style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor, flexShrink: 0 }}
          />
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.18 }}
                style={{ fontSize: 12, color: "var(--color-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {projectName}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Footer — user section */}
      {showUserSection && (
        <div style={{
          borderTop: "1px solid var(--color-divider)",
          padding: collapsed ? "10px 0" : "10px 12px",
          flexShrink: 0, overflow: "hidden",
          display: "flex", flexDirection: "column", gap: 6,
        }}>
          <AnimatePresence>
            {!collapsed && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}
              >
                <div style={{
                  width: 26, height: 26, borderRadius: "50%", flexShrink: 0,
                  background: "var(--color-accent-dim)", border: "1px solid var(--color-accent-border)",
                  display: "grid", placeItems: "center",
                  fontSize: 11, fontWeight: 700, color: "var(--color-accent)",
                }}>
                  {user.email.charAt(0).toUpperCase()}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 11, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {user.email}
                  </div>
                  <span style={{
                    fontSize: 9, padding: "1px 5px", borderRadius: 3,
                    background: user.role === "admin" ? "rgba(145,132,217,.18)" : "rgba(233,233,237,.08)",
                    color: user.role === "admin" ? "var(--color-accent)" : "var(--color-muted)",
                    fontWeight: 600, textTransform: "uppercase", letterSpacing: ".04em",
                  }}>
                    {user.role}
                  </span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <motion.button
            onClick={handleLogout}
            title={collapsed ? "Log out" : undefined}
            whileHover={{ backgroundColor: "rgba(239,68,68,.08)", color: "#f87171" }}
            style={{
              width: "100%", display: "flex", alignItems: "center",
              gap: 8, padding: collapsed ? "6px 0" : "6px 8px",
              justifyContent: collapsed ? "center" : "flex-start",
              background: "transparent", border: "none",
              borderRadius: "var(--radius-md)",
              color: "rgba(233,233,237,.4)", cursor: "pointer",
              fontFamily: "var(--font-sans)", fontSize: 12,
              transition: "background .12s, color .12s",
            }}
          >
            <span style={{ flexShrink: 0, display: "flex" }}><Icon d={ICONS.logout} /></span>
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -6 }}
                  transition={{ duration: 0.15 }}
                >
                  Log out
                </motion.span>
              )}
            </AnimatePresence>
          </motion.button>
        </div>
      )}
    </motion.aside>
  )
}

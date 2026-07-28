import { useNavigate, useLocation, useParams } from "react-router-dom"

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
  home:      "M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z M9 22V12h6v10",
  projects:  "M3 7h18M3 12h18M3 17h18",
  pipeline:  "M12 3v18M3 12h18",
  activity:  "M22 12h-4l-3 9L9 3l-3 9H2",
  artifacts: "M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z",
  files:     "M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z M13 2v7h7",
  chat:      "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
  metrics:   "M18 20V10M12 20V4M6 20v-6",
  agents:    "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2 M23 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75",
  settings:  "M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z",
  help:      "M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3 M12 17h.01",
  collapse:  "M15 18l-6-6 6-6",
}

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

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + "/")

  const statusColor = projectStatus === "running" ? "var(--color-accent)"
    : projectStatus === "complete" ? "var(--color-success)"
    : projectStatus === "failed"   ? "var(--color-error)"
    : projectStatus === "paused"   ? "var(--color-warning)"
    : "rgba(233,233,237,.25)"

  function NavBtn({ icon, label, to, active, onClick }: NavItem) {
    const handleClick = () => { if (to) navigate(to); else onClick?.() }
    return (
      <button onClick={handleClick} title={collapsed ? label : undefined}
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
          transition: "background .12s, color .12s", whiteSpace: "nowrap", overflow: "hidden",
          marginLeft: collapsed ? 0 : -2,
        }}
        onMouseEnter={e => { if (!active) e.currentTarget.style.background = "rgba(233,233,237,.05)"; e.currentTarget.style.color = "var(--color-text)" }}
        onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = active ? "var(--color-accent)" : "rgba(233,233,237,.6)" }}>
        <span style={{ flexShrink: 0, display: "flex" }}>{icon}</span>
        {!collapsed && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>}
      </button>
    )
  }

  function SectionLabel({ label }: { label: string }) {
    if (collapsed) return <div style={{ height: 1, background: "var(--color-divider)", margin: "8px 10px" }} />
    return <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "rgba(233,233,237,.3)", padding: "12px 12px 4px" }}>{label}</div>
  }

  return (
    <aside style={{
      position: "relative", display: "flex", flexDirection: "column",
      width: collapsed ? "var(--sb-col)" : "var(--sb-w)",
      minWidth: collapsed ? "var(--sb-col)" : "var(--sb-w)",
      background: "var(--color-surface)",
      borderRight: "1px solid var(--color-divider)",
      transition: `width var(--sb-dur) var(--sb-ease), min-width var(--sb-dur) var(--sb-ease)`,
      overflow: "hidden", zIndex: 10, flexShrink: 0,
    }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "space-between", padding: collapsed ? "0" : "0 8px", height: 56, borderBottom: "1px solid var(--color-divider)", flexShrink: 0, gap: 4, overflow: "hidden" }}>
        {!collapsed && (
          <a href="/" style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--color-text)", textDecoration: "none", flex: 1, overflow: "hidden", minWidth: 0 }}>
            <span style={{ width: 28, height: 28, borderRadius: 7, background: "var(--color-accent)", display: "grid", placeItems: "center", flexShrink: 0 }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </span>
            <span style={{ fontSize: 13.5, fontWeight: 700, letterSpacing: "-.025em", whiteSpace: "nowrap", overflow: "hidden" }}>AI DevOS</span>
          </a>
        )}
        {collapsed && (
          <a href="/" style={{ width: 28, height: 28, borderRadius: 7, background: "var(--color-accent)", display: "grid", placeItems: "center" }}>
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          </a>
        )}
        {!collapsed && (
          <button onClick={() => setCollapsed(true)} title="Collapse sidebar"
            style={{ width: 28, height: 28, borderRadius: 7, border: "1px solid var(--color-divider)", background: "transparent", cursor: "pointer", display: "grid", placeItems: "center", color: "rgba(233,233,237,.4)", flexShrink: 0, transition: "background .12s, border-color .12s, color .12s" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--color-accent-dim)"; e.currentTarget.style.borderColor = "var(--color-accent-border)"; e.currentTarget.style.color = "var(--color-accent)" }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderColor = "var(--color-divider)"; e.currentTarget.style.color = "rgba(233,233,237,.4)" }}>
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
        )}
        {collapsed && (
          <button onClick={() => setCollapsed(false)} title="Expand sidebar"
            style={{ position: "absolute", bottom: -1, right: -12, width: 20, height: 20, borderRadius: "0 6px 6px 0", border: "1px solid var(--color-divider)", borderLeft: "none", background: "var(--color-surface)", cursor: "pointer", display: "grid", placeItems: "center", color: "rgba(233,233,237,.4)", transition: "color .12s" }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-accent)" }}
            onMouseLeave={e => { e.currentTarget.style.color = "rgba(233,233,237,.4)" }}>
            <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        )}
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "8px 0", scrollbarWidth: "thin", scrollbarColor: "var(--color-divider) transparent" }}>

        <SectionLabel label="Navigate" />
        <NavBtn icon={<Icon d={ICONS.home} />}     label="Home"     to="/"         active={location.pathname === "/"} />
        <NavBtn icon={<Icon d={ICONS.projects} />}  label="Projects"  to="/projects" active={location.pathname === "/projects"} />

        {projectId && (
          <>
            <SectionLabel label="Project" />
            <NavBtn icon={<Icon d={ICONS.activity} />}  label="Activity"  to={`/projects/${projectId}`} active={isActive(`/projects/${projectId}`)} />
            <NavBtn icon={<Icon d={ICONS.files} />}     label="Files"     to={`/projects/${projectId}?tab=files`} active={false} />
            <NavBtn icon={<Icon d={ICONS.artifacts} />} label="Artifacts" to={`/projects/${projectId}?tab=artifacts`} active={false} />
            <NavBtn icon={<Icon d={ICONS.metrics} />}   label="Metrics"   to={`/projects/${projectId}?tab=metrics`} active={false} />
            <NavBtn icon={<Icon d={ICONS.chat} />}      label="Chat"      to={`/projects/${projectId}?tab=chat`} active={false} />
          </>
        )}

        <SectionLabel label="System" />
        <NavBtn icon={<Icon d={ICONS.agents} />}   label="Agents"   to="/projects" active={false} />
        <NavBtn icon={<Icon d={ICONS.settings} />} label="Settings" to="/projects" active={false} />
        <NavBtn icon={<Icon d={ICONS.help} />}     label="Help"     to="/" active={false} />
      </div>

      {/* Footer — project status */}
      {projectId && projectName && (
        <div style={{ borderTop: "1px solid var(--color-divider)", padding: collapsed ? "12px 0" : "10px 12px", display: "flex", alignItems: "center", gap: 8, justifyContent: collapsed ? "center" : "flex-start", flexShrink: 0, overflow: "hidden" }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor, flexShrink: 0, ...(projectStatus === "running" ? { animation: "pulse-o 1.4s ease-in-out infinite" } : {}) }} />
          {!collapsed && (
            <span style={{ fontSize: 12, color: "var(--color-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{projectName}</span>
          )}
        </div>
      )}
    </aside>
  )
}

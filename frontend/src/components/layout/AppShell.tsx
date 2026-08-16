import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom"
import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useAuth } from "../../lib/auth"
import { api, type ReadyStatus } from "../../lib/api"
import { ToastProvider } from "../ui/Toast"

const NAV_ITEMS = [
  { to: "/",           label: "Home",       icon: HomeIcon },
  { to: "/projects",   label: "Projects",   icon: FolderIcon },
  { to: "/analytics",  label: "Analytics",  icon: ChartIcon },
  { to: "/settings",   label: "Settings",   icon: GearIcon },
]

const ADMIN_ITEM = { to: "/admin", label: "Admin", icon: ShieldIcon }

// ── Sidebar width constants ───────────────────────────────────────────────────
const SB_EXPANDED = 200
const SB_COLLAPSED = 52

export default function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [health, setHealth] = useState<ReadyStatus | null>(null)

  useEffect(() => {
    api.ready().then(setHealth).catch(() => setHealth(null))
    const id = setInterval(() => {
      api.ready().then(setHealth).catch(() => setHealth(null))
    }, 30_000)
    return () => clearInterval(id)
  }, [])

  const handleLogout = async () => {
    await logout()
    navigate("/login")
  }

  const navItems = user?.role === "admin" ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS

  return (
    <ToastProvider>
      <div className="app-shell">

        {/* Sidebar — spring-animated width */}
        <motion.nav
          animate={{ width: collapsed ? SB_COLLAPSED : SB_EXPANDED, minWidth: collapsed ? SB_COLLAPSED : SB_EXPANDED }}
          transition={{ type: "spring", stiffness: 320, damping: 34 }}
          className="app-sidebar"
          style={{ overflow: "hidden" }}
        >
          {/* Brand */}
          <div className="sidebar-header">
            <div className="sidebar-logo">AI</div>
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  className="sidebar-brand"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.18 }}
                >
                  DevOS
                </motion.span>
              )}
            </AnimatePresence>
            <motion.button
              className="btn btn-ghost btn-icon btn-sm"
              style={{ marginLeft: "auto", flexShrink: 0 }}
              onClick={() => setCollapsed(c => !c)}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.92 }}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                {collapsed
                  ? <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                  : <path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                }
              </svg>
            </motion.button>
          </div>

          {/* Nav */}
          <div className="sidebar-nav">
            <AnimatePresence>
              {!collapsed && (
                <motion.div
                  className="nav-section-label"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  Navigation
                </motion.div>
              )}
            </AnimatePresence>

            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
                title={collapsed ? item.label : undefined}
              >
                <item.icon />
                <AnimatePresence>
                  {!collapsed && (
                    <motion.span
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -8 }}
                      transition={{ duration: 0.18 }}
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </NavLink>
            ))}
          </div>

          {/* Footer */}
          <div className="sidebar-footer">
            {/* System health */}
            <AnimatePresence>
              {!collapsed && health && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px 10px", fontSize: 11, color: "var(--text-muted)", overflow: "hidden" }}
                >
                  <div className={`health-dot ${health.status === "ready" ? "ready" : "degraded"}`} />
                  <span>{health.status === "ready" ? "System ready" : "Degraded"}</span>
                  {health.model && <span style={{ marginLeft: "auto", color: "var(--text-dim)" }}>{health.model}</span>}
                </motion.div>
              )}
            </AnimatePresence>

            {/* User info */}
            <div
              className="nav-item"
              style={{ cursor: "default" }}
              title={collapsed ? (user?.email ?? "") : undefined}
            >
              <UserIcon />
              <AnimatePresence>
                {!collapsed && (
                  <motion.div
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.18 }}
                    style={{ flex: 1, overflow: "hidden", display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <div style={{ flex: 1, overflow: "hidden" }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {user?.anonymous ? "Anonymous" : (user?.email ?? "Anonymous")}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "capitalize" }}>
                        {user?.role ?? "viewer"}
                      </div>
                    </div>
                    {user?.anonymous ? (
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: 11, padding: "3px 8px" }}
                        onClick={() => navigate("/login")}
                        title="Sign in or register"
                      >
                        Sign In
                      </button>
                    ) : (
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={handleLogout} title="Sign out">
                        <LogoutIcon />
                      </button>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.nav>

        {/* Main content with animated route transitions */}
        <main className="app-main">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22, ease: "easeInOut" }}
              style={{ width: "100%", height: "100%" }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>

      </div>
    </ToastProvider>
  )
}

/* ── Inline SVG icons (no dependency needed) ──────────────── */
function HomeIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 6l6-4.5L14 6v7.5a1 1 0 01-1 1H3a1 1 0 01-1-1V6z"/>
      <path d="M6 14V8h4v6"/>
    </svg>
  )
}

function FolderIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 4.5A1.5 1.5 0 012.5 3h3l1.5 2H13.5A1.5 1.5 0 0115 6.5v6A1.5 1.5 0 0113.5 14h-11A1.5 1.5 0 011 12.5v-8z"/>
    </svg>
  )
}

function ChartIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="8" width="3" height="7" rx="0.5"/>
      <rect x="6" y="4" width="3" height="11" rx="0.5"/>
      <rect x="11" y="1" width="3" height="14" rx="0.5"/>
    </svg>
  )
}

function GearIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="2.5"/>
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M2.93 2.93l1.41 1.41M11.66 11.66l1.41 1.41M2.93 13.07l1.41-1.41M11.66 4.34l1.41-1.41"/>
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1L2 4v4c0 3.31 2.68 6.41 6 7 3.32-.59 6-3.69 6-7V4L8 1z"/>
    </svg>
  )
}

function UserIcon() {
  return (
    <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="5" r="3"/>
      <path d="M2 14c0-3.31 2.69-6 6-6s6 2.69 6 6"/>
    </svg>
  )
}

function LogoutIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 2H3a1 1 0 00-1 1v10a1 1 0 001 1h3M10 11l4-4-4-4M14 8H6"/>
    </svg>
  )
}

import { useState } from "react"
import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--color-bg)" }}>
      <Sidebar
        collapsed={collapsed}
        setCollapsed={setCollapsed}
      />
      <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Outlet />
      </main>
    </div>
  )
}

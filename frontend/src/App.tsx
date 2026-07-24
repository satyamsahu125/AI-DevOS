import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/layouts/AppShell"
import { Dashboard } from "@/pages/Dashboard"
import { Projects } from "@/pages/Projects"
import { AgentsPage } from "@/pages/AgentsPage"
import { MemoryPage } from "@/pages/MemoryPage"
import { SettingsPage } from "@/pages/SettingsPage"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:projectId" element={<Projects />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App

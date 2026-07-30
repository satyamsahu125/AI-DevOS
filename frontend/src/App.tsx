import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { LandingPage } from "./pages/LandingPage"
import { ProjectsPage } from "./pages/ProjectsPage"
import { WorkspacePage } from "./pages/WorkspacePage"
import { SettingsPage } from "./pages/SettingsPage"
import { AppLayout } from "./components/layout/AppLayout"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route element={<AppLayout />}>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<WorkspacePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

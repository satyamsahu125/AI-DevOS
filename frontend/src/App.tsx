import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { ProjectsPage } from "./pages/ProjectsPage"
import { WorkspacePage } from "./pages/WorkspacePage"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<WorkspacePage />} />
        <Route path="*" element={<Navigate to="/projects" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom"
import { LandingPage } from "./pages/LandingPage"
import { LoginPage } from "./pages/LoginPage"
import { ProjectsPage } from "./pages/ProjectsPage"
import { WorkspacePage } from "./pages/WorkspacePage"
import { SettingsPage } from "./pages/SettingsPage"
import { AnalyticsPage } from "./pages/AnalyticsPage"
import { AdminPage } from "./pages/AdminPage"
import { AppLayout } from "./components/layout/AppLayout"
import { useAuth } from "./lib/auth"

function ProtectedRoute() {
  const { user, loading, authEnabled } = useAuth()

  if (loading) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100vh", background: "var(--color-bg)",
      }}>
        <style>{`@keyframes _spin { to { transform: rotate(360deg); } }`}</style>
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          border: "3px solid var(--color-divider)",
          borderTopColor: "var(--color-accent)",
          animation: "_spin 0.8s linear infinite",
        }} />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<WorkspacePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

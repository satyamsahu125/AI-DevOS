import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom"
import { useEffect } from "react"
import { AnimatePresence } from "framer-motion"
import { AuthProvider, useAuth } from "./lib/auth"
import { setTokenProvider } from "./lib/api"
import AppShell from "./components/layout/AppShell"
import { PageTransition } from "./components/layout/PageTransition"
import { LandingPage } from "./pages/LandingPage"
import LoginPage from "./pages/LoginPage"
import ProjectsPage from "./pages/ProjectsPage"
import WorkspacePage from "./pages/WorkspacePage"
import AnalyticsPage from "./pages/AnalyticsPage"
import SettingsPage from "./pages/SettingsPage"
import AdminPage from "./pages/AdminPage"

function TokenBridge() {
  const { getToken } = useAuth()
  useEffect(() => { setTokenProvider(getToken) }, [getToken])
  return null
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
      <div className="spinner spinner-lg" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
      <div className="spinner spinner-lg" />
    </div>
  )

  const isRealUser = user && !user.anonymous

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageTransition><LandingPage /></PageTransition>} />
        <Route path="/login" element={isRealUser ? <Navigate to="/projects" replace /> : <PageTransition><LoginPage initialTab="signin" /></PageTransition>} />
        <Route path="/register" element={isRealUser ? <Navigate to="/projects" replace /> : <PageTransition><LoginPage initialTab="register" /></PageTransition>} />
        <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
          <Route path="/projects" element={<PageTransition><ProjectsPage /></PageTransition>} />
          <Route path="/projects/:projectId" element={<PageTransition><WorkspacePage /></PageTransition>} />
          <Route path="/analytics" element={<PageTransition><AnalyticsPage /></PageTransition>} />
          <Route path="/settings" element={<PageTransition><SettingsPage /></PageTransition>} />
          <Route path="/admin" element={<PageTransition><AdminPage /></PageTransition>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <TokenBridge />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}

import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { App } from "./App"
import { AuthProvider, useAuth } from "./lib/auth"
import { setTokenProvider } from "./lib/api"

function AppWithAuth() {
  const { getToken } = useAuth()

  useEffect(() => {
    setTokenProvider(getToken)
  }, [getToken])

  return <App />
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <AppWithAuth />
    </AuthProvider>
  </StrictMode>,
)

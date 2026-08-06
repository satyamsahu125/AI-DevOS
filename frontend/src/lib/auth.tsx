/**
 * AuthContext — JWT token management for AI DevOS (R8).
 *
 * When AUTH_ENABLED=false on the backend (default), every request returns
 * as an anonymous admin and no login is required. The context detects this
 * case via the /auth/me endpoint: if it returns a 401 we assume auth is
 * disabled and set a synthetic "anonymous" user so the rest of the UI never
 * has to branch on "is auth on?".
 *
 * Token storage:
 *   - Access token: React state only (in-memory) — never written to disk
 *   - Refresh token: sessionStorage — survives page refresh, cleared on tab close
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"

export interface AuthUser {
  user_id: string
  email: string
  role: "admin" | "developer" | "viewer"
  anonymous: boolean
}

interface AuthState {
  user: AuthUser | null
  /** true while the initial /auth/me probe is in flight */
  loading: boolean
  authEnabled: boolean
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  getToken: () => string | null
}

const AuthContext = createContext<(AuthState & AuthActions) | null>(null)

const REFRESH_KEY = "devos_refresh_token"
const ANON_USER: AuthUser = { user_id: "anonymous", email: "anonymous", role: "admin", anonymous: true }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)
  const accessTokenRef = useRef<string | null>(null)

  const getToken = useCallback(() => accessTokenRef.current, [])

  /** Try to load persisted session from stored refresh token */
  const tryRestoreSession = useCallback(async () => {
    const stored = sessionStorage.getItem(REFRESH_KEY)
    if (!stored) return false
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: stored }),
      })
      if (!res.ok) { sessionStorage.removeItem(REFRESH_KEY); return false }
      const data = await res.json()
      accessTokenRef.current = data.access_token
      if (data.refresh_token) sessionStorage.setItem(REFRESH_KEY, data.refresh_token)
      return true
    } catch { return false }
  }, [])

  /** Probe /auth/me — determines if auth is enabled and who's logged in */
  const probe = useCallback(async () => {
    setLoading(true)
    try {
      // If we have a stored refresh token, try to restore the session first
      const restored = await tryRestoreSession()

      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (accessTokenRef.current) headers["Authorization"] = `Bearer ${accessTokenRef.current}`

      const res = await fetch("/api/auth/me", { headers })

      if (res.status === 401) {
        // Auth is enabled but we're not logged in
        setAuthEnabled(true)
        setUser(null)
        return
      }

      if (res.status === 404 || res.status === 422) {
        // Auth is disabled — backend returns 404 for /auth/* when AUTH_ENABLED=false
        setAuthEnabled(false)
        setUser(ANON_USER)
        return
      }

      if (res.ok) {
        const me = await res.json()
        setAuthEnabled(true)
        if (!restored && !accessTokenRef.current) {
          // Got a 200 without a token — auth must be disabled (returns anon user)
          setUser({ ...ANON_USER, email: me.email ?? "anonymous", role: me.role ?? "admin" })
          setAuthEnabled(false)
        } else {
          setUser({ user_id: me.user_id, email: me.email, role: me.role, anonymous: false })
        }
      } else {
        // Unexpected — treat as auth disabled
        setAuthEnabled(false)
        setUser(ANON_USER)
      }
    } catch {
      // Network error — assume auth disabled for resilience
      setAuthEnabled(false)
      setUser(ANON_USER)
    } finally {
      setLoading(false)
    }
  }, [tryRestoreSession])

  useEffect(() => { probe() }, [probe])

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? "Login failed")
    }
    const data = await res.json()
    accessTokenRef.current = data.access_token
    if (data.refresh_token) sessionStorage.setItem(REFRESH_KEY, data.refresh_token)
    setUser({ user_id: data.user_id, email: data.email, role: data.role, anonymous: false })
    setAuthEnabled(true)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail ?? "Registration failed")
    }
    // Auto-login after register
    await login(email, password)
  }, [login])

  const logout = useCallback(async () => {
    const token = accessTokenRef.current
    if (token) {
      const stored = sessionStorage.getItem(REFRESH_KEY)
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ refresh_token: stored }),
      }).catch(() => {})
    }
    accessTokenRef.current = null
    sessionStorage.removeItem(REFRESH_KEY)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, authEnabled, login, register, logout, getToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

/** Returns true if the current user has at least the given role */
export function hasRole(user: AuthUser | null, role: "admin" | "developer" | "viewer"): boolean {
  if (!user) return false
  const ranks = { admin: 3, developer: 2, viewer: 1 }
  return (ranks[user.role] ?? 0) >= (ranks[role] ?? 0)
}

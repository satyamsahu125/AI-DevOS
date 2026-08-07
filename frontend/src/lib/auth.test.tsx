/**
 * Tests for src/lib/auth.tsx
 *
 * Covers:
 *   - hasRole() pure utility
 *   - useAuth() outside provider guard
 *   - AuthProvider probe(): 401, 404/422, network error, session restore
 *   - AuthProvider login(): success (sets user from /auth/me), failure (throws)
 *   - AuthProvider logout(): clears user + token
 */

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { AuthProvider, useAuth, hasRole, type AuthUser } from "./auth"

// ─── hasRole() ───────────────────────────────────────────────────────────────

describe("hasRole()", () => {
  const admin: AuthUser   = { user_id: "1", email: "a", role: "admin",     anonymous: false }
  const dev: AuthUser     = { user_id: "2", email: "b", role: "developer", anonymous: false }
  const viewer: AuthUser  = { user_id: "3", email: "c", role: "viewer",    anonymous: false }

  it("returns false for null user", () => {
    expect(hasRole(null, "viewer")).toBe(false)
  })

  it("admin passes all role checks", () => {
    expect(hasRole(admin, "admin")).toBe(true)
    expect(hasRole(admin, "developer")).toBe(true)
    expect(hasRole(admin, "viewer")).toBe(true)
  })

  it("developer passes developer and viewer, not admin", () => {
    expect(hasRole(dev, "admin")).toBe(false)
    expect(hasRole(dev, "developer")).toBe(true)
    expect(hasRole(dev, "viewer")).toBe(true)
  })

  it("viewer passes only viewer", () => {
    expect(hasRole(viewer, "admin")).toBe(false)
    expect(hasRole(viewer, "developer")).toBe(false)
    expect(hasRole(viewer, "viewer")).toBe(true)
  })
})

// ─── useAuth outside AuthProvider ────────────────────────────────────────────

describe("useAuth()", () => {
  it("throws when used outside AuthProvider", () => {
    function Bad() {
      useAuth()
      return null
    }
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() => render(<Bad />)).toThrow("useAuth must be used within AuthProvider")
    spy.mockRestore()
  })
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Minimal consumer that exposes auth state as data-testid spans */
function StatusDisplay() {
  const { user, loading, authEnabled } = useAuth()
  if (loading) return <span data-testid="loading" />
  return (
    <>
      <span data-testid="user">{user?.email ?? "null"}</span>
      <span data-testid="anon">{String(user?.anonymous ?? false)}</span>
      <span data-testid="auth-enabled">{String(authEnabled)}</span>
    </>
  )
}

function renderProvider() {
  return render(
    <AuthProvider>
      <StatusDisplay />
    </AuthProvider>,
  )
}

/** Makes a JSON Response with Content-Type set */
function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

// ─── AuthProvider probe() ─────────────────────────────────────────────────────

describe("AuthProvider probe()", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders loading indicator initially then resolves", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })))
    renderProvider()
    expect(screen.getByTestId("loading")).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
  })

  it("401 → user=null, authEnabled=true (auth on, not logged in)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })))
    renderProvider()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
    expect(screen.getByTestId("user").textContent).toBe("null")
    expect(screen.getByTestId("auth-enabled").textContent).toBe("true")
  })

  it("404 → anonymous user, authEnabled=false (auth disabled)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })))
    renderProvider()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
    expect(screen.getByTestId("user").textContent).toBe("anonymous")
    expect(screen.getByTestId("anon").textContent).toBe("true")
    expect(screen.getByTestId("auth-enabled").textContent).toBe("false")
  })

  it("422 → anonymous user, authEnabled=false", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 422 })))
    renderProvider()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
    expect(screen.getByTestId("anon").textContent).toBe("true")
    expect(screen.getByTestId("auth-enabled").textContent).toBe("false")
  })

  it("network error → anonymous user, authEnabled=false", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Network error")))
    renderProvider()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
    expect(screen.getByTestId("user").textContent).toBe("anonymous")
    expect(screen.getByTestId("auth-enabled").textContent).toBe("false")
  })

  it("restores session from stored refresh token and sets real user", async () => {
    sessionStorage.setItem("devos_refresh_token", "stored_ref")
    const mockFetch = vi.fn()
      // tryRestoreSession: POST /auth/refresh
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "tok", refresh_token: "new_ref" }),
      )
      // probe: GET /auth/me with Bearer tok
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "u1", email: "dev@x.com", role: "developer" }),
      )
    vi.stubGlobal("fetch", mockFetch)

    renderProvider()
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())

    expect(screen.getByTestId("user").textContent).toBe("dev@x.com")
    expect(screen.getByTestId("anon").textContent).toBe("false")
    expect(screen.getByTestId("auth-enabled").textContent).toBe("true")
  })
})

// ─── AuthProvider login() ─────────────────────────────────────────────────────

function LoginConsumer() {
  const { user, loading, login } = useAuth()
  const [err, setErr] = useState<string | null>(null)
  if (loading) return <span data-testid="loading" />
  return (
    <>
      <span data-testid="user">{user?.email ?? "null"}</span>
      <span data-testid="error">{err ?? ""}</span>
      <button
        data-testid="do-login"
        onClick={() =>
          login("dev@x.com", "pass1234").catch((e: Error) => setErr(e.message))
        }
      />
    </>
  )
}

describe("AuthProvider login()", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("success: sets user from /auth/me after login", async () => {
    const user = userEvent.setup()
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))         // probe /auth/me
      .mockResolvedValueOnce(                                              // POST /auth/login
        jsonResponse({ access_token: "tok", refresh_token: "reftok" }),
      )
      .mockResolvedValueOnce(                                              // GET /auth/me post-login
        jsonResponse({ user_id: "u1", email: "dev@x.com", role: "developer" }),
      )
    vi.stubGlobal("fetch", mockFetch)

    render(<AuthProvider><LoginConsumer /></AuthProvider>)
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())
    expect(screen.getByTestId("user").textContent).toBe("null")

    await user.click(screen.getByTestId("do-login"))

    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("dev@x.com"),
    )
    expect(screen.getByTestId("error").textContent).toBe("")
  })

  it("failure: throws with detail from backend", async () => {
    const user = userEvent.setup()
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))         // probe /auth/me
      .mockResolvedValueOnce(                                              // POST /auth/login → 401
        jsonResponse({ detail: "Invalid credentials" }, 401),
      )
    vi.stubGlobal("fetch", mockFetch)

    render(<AuthProvider><LoginConsumer /></AuthProvider>)
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())

    await user.click(screen.getByTestId("do-login"))

    await waitFor(() =>
      expect(screen.getByTestId("error").textContent).toBe("Invalid credentials"),
    )
    expect(screen.getByTestId("user").textContent).toBe("null")
  })

  it("failure: falls back to 'Login failed' when backend sends no detail", async () => {
    const user = userEvent.setup()
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))         // probe /auth/me
      .mockResolvedValueOnce(new Response(null, { status: 500 }))         // POST /auth/login → 500
    vi.stubGlobal("fetch", mockFetch)

    render(<AuthProvider><LoginConsumer /></AuthProvider>)
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())

    await user.click(screen.getByTestId("do-login"))

    await waitFor(() =>
      expect(screen.getByTestId("error").textContent).toBe("Login failed"),
    )
  })

  it("stores refresh token in sessionStorage on success", async () => {
    const user = userEvent.setup()
    const mockFetch = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "tok", refresh_token: "stored_ref" }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "u1", email: "dev@x.com", role: "developer" }),
      )
    vi.stubGlobal("fetch", mockFetch)

    render(<AuthProvider><LoginConsumer /></AuthProvider>)
    await waitFor(() => expect(screen.queryByTestId("loading")).toBeNull())

    await user.click(screen.getByTestId("do-login"))
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("dev@x.com"),
    )

    expect(sessionStorage.getItem("devos_refresh_token")).toBe("stored_ref")
  })
})

// ─── AuthProvider logout() ────────────────────────────────────────────────────

function LogoutConsumer() {
  const { user, loading, logout } = useAuth()
  if (loading) return <span data-testid="loading" />
  return (
    <>
      <span data-testid="user">{user?.email ?? "null"}</span>
      <button data-testid="do-logout" onClick={() => logout()} />
    </>
  )
}

describe("AuthProvider logout()", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it("clears user and removes refresh token from sessionStorage", async () => {
    const user = userEvent.setup()
    sessionStorage.setItem("devos_refresh_token", "stored_ref")
    const mockFetch = vi.fn()
      // tryRestoreSession
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "tok", refresh_token: "new_ref" }),
      )
      // probe /auth/me
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "u1", email: "dev@x.com", role: "developer" }),
      )
      // POST /auth/logout
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", mockFetch)

    render(<AuthProvider><LogoutConsumer /></AuthProvider>)
    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("dev@x.com"),
    )

    await user.click(screen.getByTestId("do-logout"))

    await waitFor(() =>
      expect(screen.getByTestId("user").textContent).toBe("null"),
    )
    expect(sessionStorage.getItem("devos_refresh_token")).toBeNull()
  })
})

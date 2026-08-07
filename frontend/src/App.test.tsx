/**
 * Tests for src/App.tsx — ProtectedRoute behavior.
 *
 * Strategy: mock all page components to simple text nodes and mock useAuth
 * to control auth state. BrowserRouter reads window.location, so
 * window.history.pushState() sets the initial path before render.
 *
 * Covers:
 *   - Loading state → shows spinner (no redirect yet)
 *   - Unauthenticated at protected route → redirects to /login
 *   - Authenticated at protected route → renders the page
 *   - Unauthenticated at / → landing page shown
 *   - Wildcard route → redirects to /
 */

import { render, screen, waitFor } from "@testing-library/react"
import { App } from "./App"
import { useAuth } from "./lib/auth"

// Mock every page so tests don't need their heavy deps (IntersectionObserver, api calls, etc.)
vi.mock("./pages/LandingPage",  () => ({ LandingPage:  () => <div>landing-page</div>  }))
vi.mock("./pages/LoginPage",    () => ({ LoginPage:    () => <div>login-page</div>    }))
vi.mock("./pages/ProjectsPage", () => ({ ProjectsPage: () => <div>projects-page</div> }))
vi.mock("./pages/WorkspacePage",() => ({ WorkspacePage:() => <div>workspace-page</div>}))
vi.mock("./pages/SettingsPage", () => ({ SettingsPage: () => <div>settings-page</div> }))
vi.mock("./pages/AnalyticsPage",() => ({ AnalyticsPage:() => <div>analytics-page</div>}))
vi.mock("./pages/AdminPage",    () => ({ AdminPage:    () => <div>admin-page</div>    }))

// AppLayout must render Outlet so nested protected routes appear
vi.mock("./components/layout/AppLayout", async () => {
  const { Outlet } = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return { AppLayout: () => <Outlet /> }
})

// Shallow-mock auth — individual tests override via vi.mocked(useAuth).mockReturnValue
vi.mock("./lib/auth", () => ({ useAuth: vi.fn() }))

// Stable mock-return builder
const authenticated = () =>
  vi.mocked(useAuth).mockReturnValue({
    user: { user_id: "u1", email: "dev@x.com", role: "developer", anonymous: false },
    loading: false,
    authEnabled: true,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getToken: vi.fn(() => "tok"),
  })

const unauthenticated = () =>
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    loading: false,
    authEnabled: true,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getToken: vi.fn(() => null),
  })

const loading = () =>
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    loading: true,
    authEnabled: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getToken: vi.fn(() => null),
  })

afterEach(() => {
  // Reset URL back to root so tests don't pollute each other
  window.history.pushState({}, "", "/")
})

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ProtectedRoute", () => {
  it("shows spinner while loading (no redirect yet)", async () => {
    loading()
    window.history.pushState({}, "", "/projects")
    render(<App />)

    // Neither login nor projects page should be rendered during loading
    expect(screen.queryByText("login-page")).toBeNull()
    expect(screen.queryByText("projects-page")).toBeNull()
  })

  it("redirects to /login when unauthenticated at a protected route", async () => {
    unauthenticated()
    window.history.pushState({}, "", "/projects")
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText("login-page")).toBeInTheDocument(),
    )
    expect(screen.queryByText("projects-page")).toBeNull()
  })

  it("renders the protected page when authenticated", async () => {
    authenticated()
    window.history.pushState({}, "", "/projects")
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText("projects-page")).toBeInTheDocument(),
    )
    expect(screen.queryByText("login-page")).toBeNull()
  })

  it("redirects unauthenticated /settings to /login", async () => {
    unauthenticated()
    window.history.pushState({}, "", "/settings")
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText("login-page")).toBeInTheDocument(),
    )
  })
})

describe("Public routes", () => {
  it("renders landing page at /", () => {
    unauthenticated()
    render(<App />)
    expect(screen.getByText("landing-page")).toBeInTheDocument()
  })

  it("renders login page at /login", () => {
    unauthenticated()
    window.history.pushState({}, "", "/login")
    render(<App />)
    expect(screen.getByText("login-page")).toBeInTheDocument()
  })

  it("redirects wildcard paths to / (landing)", () => {
    unauthenticated()
    window.history.pushState({}, "", "/does-not-exist")
    render(<App />)
    expect(screen.getByText("landing-page")).toBeInTheDocument()
  })
})

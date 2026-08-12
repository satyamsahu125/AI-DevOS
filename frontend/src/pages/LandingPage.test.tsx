/**
 * Tests for src/pages/LandingPage.tsx
 *
 * Strategy: mock useAuth and useNavigate; stub IntersectionObserver (jsdom lacks it).
 * Render inside MemoryRouter for react-router-dom context.
 *
 * Covers:
 *   - Renders without crashing (hero headline visible)
 *   - Shows "Start Building" CTA when not logged in
 *   - Redirects to /projects when user is already authenticated
 *   - Does NOT redirect while auth is still loading
 */

import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { LandingPage } from "./LandingPage"
import { useAuth } from "../lib/auth"

// ─── Module mocks ─────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }))

// ─── Global stubs for jsdom ────────────────────────────────────────────────────
// NOTE: must be beforeEach, not beforeAll.
// setup.ts calls vi.restoreAllMocks() after every test, which resets the stub's
// internal vi.fn() instances.  Re-stubbing each time keeps the mock fresh.

beforeEach(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn().mockImplementation(() => ({
      observe:    vi.fn(),
      unobserve:  vi.fn(),
      disconnect: vi.fn(),
    })),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  )
}

function setupAuth(user: Parameters<typeof vi.mocked<typeof useAuth>>[0] extends (...a: infer A) => infer R ? R : never) {
  vi.mocked(useAuth).mockReturnValue(user)
}

beforeEach(() => {
  mockNavigate.mockClear()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("LandingPage", () => {
  it("renders the hero headline without crashing", () => {
    setupAuth({
      user: null, loading: false, authEnabled: true,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), getToken: vi.fn(() => null),
    })
    renderLanding()
    // The headline "Software builds itself." is split across two lines
    expect(screen.getByText(/software/i)).toBeInTheDocument()
  })

  it("shows 'Start Building' CTA when not logged in", () => {
    setupAuth({
      user: null, loading: false, authEnabled: true,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), getToken: vi.fn(() => null),
    })
    renderLanding()
    // Multiple "Start Building" buttons may exist (nav + hero + cta)
    expect(screen.getAllByText(/start building/i).length).toBeGreaterThan(0)
  })

  it("does NOT redirect while auth is loading", () => {
    setupAuth({
      user: null, loading: true, authEnabled: false,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), getToken: vi.fn(() => null),
    })
    renderLanding()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it("redirects to /projects when user is already authenticated", async () => {
    setupAuth({
      user: { user_id: "u1", email: "dev@x.com", role: "developer", anonymous: false },
      loading: false,
      authEnabled: true,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), getToken: vi.fn(() => "tok"),
    })
    renderLanding()

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/projects", { replace: true }),
    )
  })

  it("shows 'Go to Projects' nav button when user is logged in", () => {
    setupAuth({
      user: { user_id: "u1", email: "dev@x.com", role: "developer", anonymous: false },
      loading: false,
      authEnabled: true,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), getToken: vi.fn(() => "tok"),
    })
    renderLanding()
    expect(screen.getByText(/go to projects/i)).toBeInTheDocument()
  })
})

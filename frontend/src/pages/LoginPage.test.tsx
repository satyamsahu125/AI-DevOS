/**
 * Tests for src/pages/LoginPage.tsx
 *
 * Strategy: mock useAuth so tests control login/register behavior,
 * mock useNavigate to spy on redirects. Render inside MemoryRouter
 * so react-router-dom hooks have context.
 *
 * Covers:
 *   - Renders email/password fields (sign-in mode)
 *   - Submit button is disabled when fields are empty
 *   - Calls login() and navigates to /projects on success
 *   - Shows error message when login() throws
 *   - Toggles to register mode (shows Confirm Password field)
 *   - Register: shows "Passwords don't match" when confirmation differs
 *   - Register: calls register() and navigates on success
 */

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { LoginPage } from "./LoginPage"
import { useAuth } from "../lib/auth"

// ─── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }))

// ─── Helpers ──────────────────────────────────────────────────────────────────

const mockLogin    = vi.fn()
const mockRegister = vi.fn()

function setupAuth(overrides?: { login?: typeof mockLogin; register?: typeof mockRegister }) {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    loading: false,
    authEnabled: true,
    login:    overrides?.login    ?? mockLogin,
    register: overrides?.register ?? mockRegister,
    logout:   vi.fn(),
    getToken: vi.fn(() => null),
  })
}

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockNavigate.mockClear()
  mockLogin.mockClear()
  mockRegister.mockClear()
  setupAuth()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("LoginPage — sign-in mode", () => {
  it("renders email and password fields with submit button", () => {
    renderLogin()
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument()
  })

  it("submit button is disabled when fields are empty", () => {
    renderLogin()
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled()
  })

  it("submit button enables after typing email and password", async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByPlaceholderText("you@example.com"), "dev@x.com")
    await user.type(screen.getByPlaceholderText("••••••••"), "pass1234")

    expect(screen.getByRole("button", { name: /sign in/i })).not.toBeDisabled()
  })

  it("calls login() with trimmed email + password on submit", async () => {
    const user = userEvent.setup()
    mockLogin.mockResolvedValue(undefined)
    renderLogin()

    await user.type(screen.getByPlaceholderText("you@example.com"), "  dev@x.com  ")
    await user.type(screen.getByPlaceholderText("••••••••"), "pass1234")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith("dev@x.com", "pass1234"))
  })

  it("navigates to /projects after successful login", async () => {
    const user = userEvent.setup()
    mockLogin.mockResolvedValue(undefined)
    renderLogin()

    await user.type(screen.getByPlaceholderText("you@example.com"), "dev@x.com")
    await user.type(screen.getByPlaceholderText("••••••••"), "pass1234")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/projects", { replace: true }),
    )
  })

  it("shows error message when login() throws", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new Error("Invalid credentials"))
    renderLogin()

    await user.type(screen.getByPlaceholderText("you@example.com"), "bad@x.com")
    await user.type(screen.getByPlaceholderText("••••••••"), "wrongpass")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument(),
    )
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it("shows 'Authentication failed' when login() throws a non-Error value", async () => {
    const user = userEvent.setup()
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
    mockLogin.mockRejectedValue("string error")
    renderLogin()

    await user.type(screen.getByPlaceholderText("you@example.com"), "bad@x.com")
    await user.type(screen.getByPlaceholderText("••••••••"), "wrongpass")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByText("Authentication failed")).toBeInTheDocument(),
    )
  })
})

describe("LoginPage — register mode", () => {
  async function switchToRegister(user: ReturnType<typeof userEvent.setup>) {
    renderLogin()
    await user.click(screen.getByRole("button", { name: /register/i }))
  }

  it("shows Confirm Password field in register mode", async () => {
    const user = userEvent.setup()
    await switchToRegister(user)

    // In register mode there are TWO password fields (password + confirm)
    const passwordFields = screen.getAllByPlaceholderText("••••••••")
    expect(passwordFields).toHaveLength(2)
  })

  it("shows 'Passwords don't match' error before submitting", async () => {
    const user = userEvent.setup()
    await switchToRegister(user)

    await user.type(screen.getByPlaceholderText("you@example.com"), "dev@x.com")
    const [passwordField, confirmField] = screen.getAllByPlaceholderText("••••••••")
    await user.type(passwordField, "pass1234")
    await user.type(confirmField, "different")
    await user.click(screen.getByRole("button", { name: /create account/i }))

    await waitFor(() =>
      expect(screen.getByText("Passwords don't match")).toBeInTheDocument(),
    )
    expect(mockRegister).not.toHaveBeenCalled()
  })

  it("calls register() and navigates to /projects on success", async () => {
    const user = userEvent.setup()
    mockRegister.mockResolvedValue(undefined)
    await switchToRegister(user)

    await user.type(screen.getByPlaceholderText("you@example.com"), "new@x.com")
    const [passwordField, confirmField] = screen.getAllByPlaceholderText("••••••••")
    await user.type(passwordField, "pass1234")
    await user.type(confirmField, "pass1234")
    await user.click(screen.getByRole("button", { name: /create account/i }))

    await waitFor(() =>
      expect(mockRegister).toHaveBeenCalledWith("new@x.com", "pass1234"),
    )
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/projects", { replace: true }),
    )
  })
})

import "@testing-library/jest-dom"
import { afterEach, vi } from "vitest"
import { cleanup } from "@testing-library/react"

// Clean up the DOM after every test so state never leaks between tests
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// Silence console.error in tests unless explicitly needed
const originalError = console.error
beforeEach(() => {
  console.error = (...args: unknown[]) => {
    // Suppress React prop-type / act() warnings that are noise in test output
    if (
      typeof args[0] === "string" &&
      (args[0].includes("Warning: ReactDOM.render") ||
        args[0].includes("act(") ||
        args[0].includes("Not implemented"))
    ) {
      return
    }
    originalError(...args)
  }
})

afterEach(() => {
  console.error = originalError
})

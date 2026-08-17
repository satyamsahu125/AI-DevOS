import "@testing-library/jest-dom"
import { afterEach, vi } from "vitest"
import { cleanup } from "@testing-library/react"

// ── Browser API mocks ─────────────────────────────────────────────────────────
// framer-motion's useInView / whileInView calls IntersectionObserver on mount.
// jsdom does not implement this API, so we shim it to prevent ReferenceError
// in any test that renders a component with framer-motion viewport animations.
if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = class IntersectionObserver {
    readonly root: Element | Document | null = null
    readonly rootMargin: string = "0px"
    readonly thresholds: ReadonlyArray<number> = []
    observe()    { /* no-op */ }
    unobserve()  { /* no-op */ }
    disconnect() { /* no-op */ }
    takeRecords(): IntersectionObserverEntry[] { return [] }
  }
}

// ResizeObserver is similarly absent in jsdom — some layout components use it.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe()    { /* no-op */ }
    unobserve()  { /* no-op */ }
    disconnect() { /* no-op */ }
  }
}

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

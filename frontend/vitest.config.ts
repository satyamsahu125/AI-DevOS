/**
 * Standalone Vitest config — intentionally excludes @tailwindcss/vite.
 *
 * The tailwindcss vite plugin initialises a native lightningcss binary on
 * startup which crashes in headless/CI environments that lack the matching
 * glibc version. Unit tests never need CSS compilation, so we drop the
 * plugin here and import only the react plugin.
 *
 * vite.config.ts is still used for `vite dev` / `vite build`.
 */

import path from "node:path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/main.tsx"],
    },
  },
})

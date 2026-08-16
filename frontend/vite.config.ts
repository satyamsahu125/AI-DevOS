import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
        // Suppress ECONNABORTED / ECONNRESET noise that fires when the backend
        // closes a WebSocket connection between stage transitions.
        configure: (proxy: any) => {
          const IGNORED = new Set(["ECONNABORTED", "ECONNRESET", "EPIPE"])
          proxy.on("error", (err: Error & { code?: string }) => {
            if (err.code && IGNORED.has(err.code)) return
            console.warn("[proxy]", err.message)
          })
        },
      },
    },
  },
} as any)

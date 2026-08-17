import { defineConfig, devices } from '@playwright/test';
import path from 'path';

/**
 * AI DevOS — Playwright E2E Configuration
 *
 * Discovery findings applied:
 * - Frontend: Vite, http://localhost:5173
 * - Backend:  FastAPI, http://localhost:8000
 * - API:      /api/v1 prefix
 * - Auth:     disabled (AUTH_ENABLED=false) — no token needed
 * - Human approval gates: disabled (REQUIRE_HUMAN_APPROVAL=false) — pipeline runs end-to-end
 *
 * Tests are serial (workers:1) because the AI pipeline has shared state per project and
 * each test can saturate the LLM concurrency limit.
 *
 * Run:
 *   npx playwright test --config e2e/playwright.config.ts
 *   npx playwright test --config e2e/playwright.config.ts e2e/tests/07-ui-smoke.spec.ts  # smoke only
 */
export default defineConfig({
  testDir: path.join(__dirname, 'tests'),
  fullyParallel: false,          // AI pipeline tests must be serial — shared state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,                    // Serial: backend has shared state per test run
  reporter: [
    ['html', { outputFolder: path.join(__dirname, 'report'), open: 'never' }],
    ['json', { outputFile: path.join(__dirname, 'results.json') }],
    ['line'],
  ],
  use: {
    baseURL: process.env.FRONTEND_URL || 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },
  webServer: [
    {
      // Backend — FastAPI via uvicorn
      command: 'cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app --log-level info',
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        ...process.env,
      },
    },
    {
      // Frontend — Vite dev server
      command: 'cd frontend && npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
